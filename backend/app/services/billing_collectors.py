"""
Escrivão AI — Billing Collectors
Coletores de custo para cada provedor externo.
Cada função retorna BillingResult ou None (provedor indisponível).

Modos:
  official_api         — Vercel, Railway (API oficial de billing/usage)
  estimated            — Supabase (Management API + cálculo por uso)
  internal_telemetry   — Serper (contagem interna × preço/1k queries)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class BillingResult:
    custo_usd: Decimal
    custo_brl: Decimal
    source: str        # "official_api" | "estimated" | "internal_telemetry"
    confidence: str    # "high" | "medium" | "low"
    raw_payload: Optional[dict] = field(default=None)
    observacao: Optional[str] = field(default=None)


# ── Vercel ─────────────────────────────────────────────────────────────────────

async def coletar_vercel(mes: str, cotacao: float) -> Optional[BillingResult]:
    """
    Coleta cobranças via GET /v1/billing/charges.
    Requer plano Pro ou Enterprise — retorna None em plano Hobby (403).
    """
    from app.core.config import settings

    token = settings.VERCEL_TOKEN
    if not token:
        logger.info("[BILLING-Vercel] VERCEL_TOKEN não configurado — skip")
        return None

    # Montar intervalo do mês
    ano, month = mes.split("-")
    import calendar
    _, ultimo_dia = calendar.monthrange(int(ano), int(month))
    date_from = f"{mes}-01T00:00:00.000Z"
    date_to   = f"{mes}-{ultimo_dia:02d}T23:59:59.999Z"

    params: dict[str, str] = {"from": date_from, "to": date_to}
    if settings.VERCEL_TEAM_ID:
        params["teamId"] = settings.VERCEL_TEAM_ID

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                "https://api.vercel.com/v1/billing/charges",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                params=params,
            )

        if resp.status_code == 403:
            logger.warning("[BILLING-Vercel] 403 — plano Hobby não tem acesso a billing API")
            return None
        if resp.status_code >= 400:
            logger.warning(f"[BILLING-Vercel] HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        # Vercel billing/charges retorna JSONL (uma linha por registro)
        import json as _json
        charges = []
        for line in resp.text.strip().splitlines():
            line = line.strip()
            if line:
                try:
                    charges.append(_json.loads(line))
                except _json.JSONDecodeError:
                    pass

        # Campos possíveis: total, amount, billedAmount (em centavos de USD)
        total_usd = sum(
            float(c.get("total", c.get("billedAmount", c.get("amount", 0))))
            for c in charges
        ) / 100

        return BillingResult(
            custo_usd=Decimal(str(round(total_usd, 4))),
            custo_brl=Decimal(str(round(total_usd * cotacao, 2))),
            source="official_api",
            confidence="high",
            raw_payload={"charges_count": len(charges), "total_usd_cents": total_usd * 100},
            observacao=f"Vercel API — {len(charges)} cobranças",
        )

    except Exception as e:
        logger.warning(f"[BILLING-Vercel] Erro: {e}", exc_info=True)
        return None


# ── Railway ────────────────────────────────────────────────────────────────────

RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"
# Consulta uso estimado por projeto do usuário atual
RAILWAY_QUERY = """
query {
  me {
    projects {
      edges {
        node {
          name
          estimatedUsage
        }
      }
    }
  }
}
"""


async def coletar_railway(mes: str, cotacao: float) -> Optional[BillingResult]:
    """
    Coleta custo estimado via GraphQL público da Railway.
    Só disponível para o período de faturamento corrente — meses históricos retornam None.
    """
    from app.core.config import settings

    token = settings.RAILWAY_TOKEN
    if not token:
        logger.info("[BILLING-Railway] RAILWAY_TOKEN não configurado — skip")
        return None

    # Railway só entrega o período corrente — verificar se o mês solicitado é o atual
    mes_atual = datetime.utcnow().strftime("%Y-%m")
    if mes != mes_atual:
        logger.info(f"[BILLING-Railway] Railway não suporta consulta histórica (solicitado: {mes})")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                RAILWAY_GQL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"query": RAILWAY_QUERY},
            )

        if resp.status_code >= 400:
            logger.warning(f"[BILLING-Railway] HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        edges = (data.get("data") or {}).get("me", {}).get("projects", {}).get("edges", [])

        total_usd = 0.0
        projetos = []
        for edge in edges:
            node = edge.get("node") or {}
            custo = float(node.get("estimatedUsage") or 0)
            total_usd += custo
            projetos.append({"nome": node.get("name"), "estimatedUsage": custo})

        return BillingResult(
            custo_usd=Decimal(str(round(total_usd, 4))),
            custo_brl=Decimal(str(round(total_usd * cotacao, 2))),
            source="official_api",
            confidence="medium",
            raw_payload={"projetos": projetos, "total_usd": total_usd},
            observacao=f"Railway GraphQL — {len(projetos)} projetos",
        )

    except Exception as e:
        logger.warning(f"[BILLING-Railway] Erro: {e}", exc_info=True)
        return None


# ── Supabase (estimativa) ──────────────────────────────────────────────────────

async def coletar_supabase(mes: str, cotacao: float) -> Optional[BillingResult]:
    """
    Supabase Management API não expõe fatura detalhada publicamente.
    Consulta métricas de uso (db_size, egress) e calcula custo estimado.
    No plano gratuito o custo é $0 dentro dos limites.
    """
    from app.core.config import settings

    token = settings.SUPABASE_MANAGEMENT_TOKEN
    if not token:
        logger.info("[BILLING-Supabase] SUPABASE_MANAGEMENT_TOKEN não configurado — skip")
        return None

    # Extrair project_ref da SUPABASE_URL (https://<ref>.supabase.co)
    supabase_url = settings.SUPABASE_URL or ""
    ref = supabase_url.replace("https://", "").split(".")[0] if supabase_url else None
    if not ref or len(ref) < 5:
        logger.warning("[BILLING-Supabase] Não foi possível extrair project_ref da SUPABASE_URL")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"https://api.supabase.com/v1/projects/{ref}/usage",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )

        if resp.status_code == 404:
            # Endpoint pode não estar disponível — retornar estimativa zero
            logger.info("[BILLING-Supabase] Endpoint de usage não disponível (404) — reportando $0")
            return BillingResult(
                custo_usd=Decimal("0.00"),
                custo_brl=Decimal("0.00"),
                source="estimated",
                confidence="low",
                observacao="Supabase — endpoint de usage indisponível, dentro do plano gratuito",
            )
        if resp.status_code >= 400:
            logger.warning(f"[BILLING-Supabase] HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        # Limites do plano gratuito
        db_bytes    = data.get("db_size_bytes", 0) or 0
        storage_bytes = data.get("storage_size_bytes", 0) or 0
        egress_bytes  = data.get("egress_bytes", 0) or 0

        DB_LIMIT_BYTES      = 500 * 1024 * 1024    # 500 MB
        STORAGE_LIMIT_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB
        EGRESS_LIMIT_BYTES  = 5 * 1024 * 1024 * 1024  # 5 GB

        # Excesso cobra ~$0.125/GB para banco e storage, $0.09/GB para egress
        excess_db      = max(0, db_bytes - DB_LIMIT_BYTES) / (1024**3)
        excess_storage = max(0, storage_bytes - STORAGE_LIMIT_BYTES) / (1024**3)
        excess_egress  = max(0, egress_bytes - EGRESS_LIMIT_BYTES) / (1024**3)

        custo_usd = (excess_db + excess_storage) * 0.125 + excess_egress * 0.09

        return BillingResult(
            custo_usd=Decimal(str(round(custo_usd, 4))),
            custo_brl=Decimal(str(round(custo_usd * cotacao, 2))),
            source="estimated",
            confidence="low",
            raw_payload={
                "db_size_mb": round(db_bytes / (1024**2), 1),
                "storage_size_mb": round(storage_bytes / (1024**2), 1),
                "egress_mb": round(egress_bytes / (1024**2), 1),
            },
            observacao="Supabase — estimativa por uso (Management API)",
        )

    except Exception as e:
        logger.warning(f"[BILLING-Supabase] Erro: {e}", exc_info=True)
        return None


# ── Serper (telemetria interna) ────────────────────────────────────────────────

async def coletar_serper(mes: str, cotacao: float, db) -> Optional[BillingResult]:
    """
    Agrega usage_events do Serper no mês e calcula custo por quantidade de queries.
    Custo por 1k queries configurável via SERPER_PRICE_PER_1K_QUERIES.
    """
    from app.core.config import settings
    from sqlalchemy import select, func
    from app.models.usage_event import UsageEvent
    from datetime import datetime

    try:
        ano, month = mes.split("-")
        inicio = datetime(int(ano), int(month), 1)
        import calendar
        _, ultimo_dia = calendar.monthrange(int(ano), int(month))
        fim = datetime(int(ano), int(month), ultimo_dia, 23, 59, 59)

        result = await db.execute(
            select(
                func.coalesce(func.sum(UsageEvent.quantity), 0).label("total_queries"),
            )
            .where(UsageEvent.provider == "serper")
            .where(UsageEvent.occurred_at >= inicio)
            .where(UsageEvent.occurred_at <= fim)
        )
        row = result.one()
        total_queries = int(row.total_queries)

        preco_por_1k = settings.SERPER_PRICE_PER_1K_QUERIES
        custo_usd = (total_queries * preco_por_1k) / 1000

        return BillingResult(
            custo_usd=Decimal(str(round(custo_usd, 6))),
            custo_brl=Decimal(str(round(custo_usd * cotacao, 2))),
            source="internal_telemetry",
            confidence="medium",
            raw_payload={"total_queries": total_queries, "price_per_1k": preco_por_1k},
            observacao=f"Serper — {total_queries} queries × US${preco_por_1k}/1k",
        )

    except Exception as e:
        logger.warning(f"[BILLING-Serper] Erro: {e}", exc_info=True)
        return None
