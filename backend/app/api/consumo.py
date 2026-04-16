"""
Escrivão AI — API de Controle de Orçamento LLM
Endpoints para dashboard financeiro: saldo, ranking por agente, histórico diário,
custos de serviços externos e configurações de orçamento.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.core.database import get_db
from app.core.config import settings
from app.models.consumo_api import ConsumoApi
from app.models.custo_externo import CustoExterno
from app.models.consulta_externa import ConsultaExterna
from app.models.inquerito import Inquerito

router = APIRouter(prefix="/consumo", tags=["Orçamento"])

SERVICOS_VALIDOS = {"vercel", "supabase", "railway", "serper", "gemini_studio", "outro"}


def _inicio_mes_atual() -> datetime:
    now = datetime.utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/saldo")
async def saldo_orcamento(db: AsyncSession = Depends(get_db)):
    """
    Retorna o saldo disponível do mês corrente.
    Fórmula: R$ 250,00 - soma de custo_brl do mês.
    """
    inicio = _inicio_mes_atual()

    result = await db.execute(
        select(
            func.coalesce(func.sum(ConsumoApi.custo_brl), 0).label("gasto_total"),
            func.coalesce(func.sum(ConsumoApi.tokens_prompt + ConsumoApi.tokens_saida), 0).label("tokens_total"),
            func.count(ConsumoApi.id).label("chamadas"),
        ).where(ConsumoApi.timestamp >= inicio)
    )
    row = result.one()

    gasto = float(row.gasto_total)
    budget = settings.BUDGET_BRL
    saldo = budget - gasto
    pct_usado = (gasto / budget * 100) if budget > 0 else 0

    return {
        "mes_referencia": inicio.strftime("%Y-%m"),
        "budget_brl": budget,
        "gasto_brl": round(gasto, 4),
        "saldo_brl": round(saldo, 4),
        "percentual_usado": round(pct_usado, 1),
        "tokens_total": int(row.tokens_total),
        "chamadas_total": int(row.chamadas),
        "alerta_ativo": gasto >= settings.BUDGET_ALERT_BRL,
        "cotacao_dolar": settings.COTACAO_DOLAR,
    }


@router.get("/ranking")
async def ranking_por_agente(db: AsyncSession = Depends(get_db)):
    """
    Ranking de gastos por agente no mês corrente.
    Útil para identificar qual componente está consumindo mais orçamento.
    """
    inicio = _inicio_mes_atual()

    result = await db.execute(
        select(
            ConsumoApi.agente,
            ConsumoApi.tier,
            func.sum(ConsumoApi.custo_brl).label("gasto_brl"),
            func.sum(ConsumoApi.custo_usd).label("gasto_usd"),
            func.sum(ConsumoApi.tokens_prompt).label("tokens_prompt"),
            func.sum(ConsumoApi.tokens_saida).label("tokens_saida"),
            func.count(ConsumoApi.id).label("chamadas"),
        )
        .where(ConsumoApi.timestamp >= inicio)
        .group_by(ConsumoApi.agente, ConsumoApi.tier)
        .order_by(func.sum(ConsumoApi.custo_brl).desc())
    )
    rows = result.all()

    return [
        {
            "agente": r.agente,
            "tier": r.tier,
            "gasto_brl": round(float(r.gasto_brl), 4),
            "gasto_usd": round(float(r.gasto_usd), 6),
            "tokens_prompt": int(r.tokens_prompt),
            "tokens_saida": int(r.tokens_saida),
            "chamadas": int(r.chamadas),
        }
        for r in rows
    ]


@router.get("/historico")
async def historico_diario(dias: int = 30, db: AsyncSession = Depends(get_db)):
    """
    Gasto diário dos últimos N dias (padrão: 30).
    Ideal para gráfico de linha no frontend.
    """
    inicio = datetime.utcnow() - timedelta(days=dias)

    result = await db.execute(
        select(
            func.date_trunc("day", ConsumoApi.timestamp).label("dia"),
            func.sum(ConsumoApi.custo_brl).label("gasto_brl"),
            func.count(ConsumoApi.id).label("chamadas"),
        )
        .where(ConsumoApi.timestamp >= inicio)
        .group_by(text("1"))
        .order_by(text("1"))
    )
    rows = result.all()

    return [
        {
            "dia": r.dia.strftime("%Y-%m-%d"),
            "gasto_brl": round(float(r.gasto_brl), 4),
            "chamadas": int(r.chamadas),
        }
        for r in rows
    ]


@router.get("/modelos")
async def ranking_por_modelo(db: AsyncSession = Depends(get_db)):
    """Breakdown de custo por modelo LLM no mês corrente."""
    inicio = _inicio_mes_atual()

    result = await db.execute(
        select(
            ConsumoApi.modelo,
            func.sum(ConsumoApi.custo_brl).label("gasto_brl"),
            func.sum(ConsumoApi.tokens_prompt + ConsumoApi.tokens_saida).label("tokens_total"),
            func.count(ConsumoApi.id).label("chamadas"),
        )
        .where(ConsumoApi.timestamp >= inicio)
        .group_by(ConsumoApi.modelo)
        .order_by(func.sum(ConsumoApi.custo_brl).desc())
    )
    rows = result.all()

    return [
        {
            "modelo": r.modelo,
            "gasto_brl": round(float(r.gasto_brl), 4),
            "tokens_total": int(r.tokens_total),
            "chamadas": int(r.chamadas),
        }
        for r in rows
    ]


# ── Custos Externos (Vercel, Supabase, Railway, Serper) ────────────────────────

class CustoExternoInput(BaseModel):
    custo_usd: float = 0.0
    custo_brl: float = 0.0
    observacao: Optional[str] = None


def _mes_atual() -> str:
    return datetime.utcnow().strftime("%Y-%m")


@router.get("/externos")
async def listar_custos_externos(mes: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Lista custos externos do mês informado (padrão: mês atual).
    Retorna também o total consolidado (Gemini + externos).
    """
    mes_ref = mes or _mes_atual()

    result = await db.execute(
        select(CustoExterno).where(CustoExterno.mes == mes_ref).order_by(CustoExterno.servico)
    )
    externos = result.scalars().all()

    # Soma Gemini do mesmo mês
    inicio_mes = datetime.strptime(mes_ref + "-01", "%Y-%m-%d")

    res_gemini = await db.execute(
        select(func.coalesce(func.sum(ConsumoApi.custo_brl), 0))
        .where(ConsumoApi.timestamp >= inicio_mes)
    )
    gemini_brl = float(res_gemini.scalar())

    externos_list = [
        {
            "servico": e.servico,
            "mes": e.mes,
            "custo_usd": float(e.custo_usd),
            "custo_brl": float(e.custo_brl),
            "observacao": e.observacao,
            "source": e.source,
            "confidence": e.confidence,
            "updated_at": e.updated_at.isoformat(),
        }
        for e in externos
    ]

    total_externos_brl = sum(e["custo_brl"] for e in externos_list)

    return {
        "mes": mes_ref,
        "gemini_brl": round(gemini_brl, 2),
        "externos": externos_list,
        "total_externos_brl": round(total_externos_brl, 2),
        "total_consolidado_brl": round(gemini_brl + total_externos_brl, 2),
    }


@router.put("/externos/{servico}")
async def salvar_custo_externo(
    servico: str,
    body: CustoExternoInput,
    mes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Salva (cria ou atualiza) o custo de um serviço externo para o mês.
    Serviços: vercel, supabase, railway, serper, gemini_studio, outro.
    """
    if servico not in SERVICOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Serviço inválido. Use: {', '.join(sorted(SERVICOS_VALIDOS))}")

    mes_ref = mes or _mes_atual()

    result = await db.execute(
        select(CustoExterno)
        .where(CustoExterno.servico == servico)
        .where(CustoExterno.mes == mes_ref)
    )
    registro = result.scalar_one_or_none()

    if registro:
        registro.custo_usd = Decimal(str(body.custo_usd))
        registro.custo_brl = Decimal(str(body.custo_brl))
        registro.observacao = body.observacao
        registro.source = "manual"
        registro.confidence = "high"
        registro.updated_at = datetime.utcnow()
    else:
        registro = CustoExterno(
            servico=servico,
            mes=mes_ref,
            custo_usd=Decimal(str(body.custo_usd)),
            custo_brl=Decimal(str(body.custo_brl)),
            observacao=body.observacao,
            source="manual",
            confidence="high",
        )
        db.add(registro)

    await db.commit()
    return {"status": "ok", "servico": servico, "mes": mes_ref, "custo_brl": float(registro.custo_brl)}


# ── Configurações de Orçamento ─────────────────────────────────────────────────

class OrcamentoConfig(BaseModel):
    budget_brl: float
    budget_alert_brl: float
    cotacao_dolar: float


@router.get("/config")
async def get_config_orcamento():
    """Retorna as configurações atuais de orçamento LLM."""
    return {
        "budget_brl": settings.BUDGET_BRL,
        "budget_alert_brl": settings.BUDGET_ALERT_BRL,
        "cotacao_dolar": settings.COTACAO_DOLAR,
    }


@router.put("/config")
async def set_config_orcamento(body: OrcamentoConfig):
    """
    Atualiza limites de orçamento em tempo de execução.
    ATENÇÃO: persiste apenas até o próximo restart. Atualize no Railway para persistir.
    """
    if body.budget_brl <= 0 or body.budget_alert_brl <= 0 or body.cotacao_dolar <= 0:
        raise HTTPException(status_code=422, detail="Todos os valores devem ser positivos.")
    if body.budget_alert_brl >= body.budget_brl:
        raise HTTPException(status_code=422, detail="Alerta deve ser menor que o limite total.")

    settings.BUDGET_BRL = body.budget_brl
    settings.BUDGET_ALERT_BRL = body.budget_alert_brl
    settings.COTACAO_DOLAR = body.cotacao_dolar

    return {
        "status": "ok",
        "aviso": "Ativo até o próximo restart. Atualize no Railway para persistir.",
        "budget_brl": settings.BUDGET_BRL,
        "budget_alert_brl": settings.BUDGET_ALERT_BRL,
        "cotacao_dolar": settings.COTACAO_DOLAR,
    }


# ── OSINT por Inquérito ────────────────────────────────────────────────────────

@router.get("/osint-por-inquerito")
async def osint_por_inquerito(db: AsyncSession = Depends(get_db)):
    """
    Agrupa o custo OSINT (direct.data) por inquérito.
    Retorna ranking dos inquéritos mais caros em consultas externas.
    """
    result = await db.execute(
        select(
            ConsultaExterna.inquerito_id,
            func.sum(ConsultaExterna.custo_estimado).label("custo_total"),
            func.count(ConsultaExterna.id).label("total_consultas"),
        )
        .group_by(ConsultaExterna.inquerito_id)
        .order_by(func.sum(ConsultaExterna.custo_estimado).desc())
        .limit(10)
    )
    rows = result.all()

    # Busca os números dos inquéritos
    inq_ids = [r.inquerito_id for r in rows]
    inq_result = await db.execute(
        select(Inquerito.id, Inquerito.numero).where(Inquerito.id.in_(inq_ids))
    )
    inq_map = {str(r.id): r.numero for r in inq_result.all()}

    return [
        {
            "inquerito_id": str(r.inquerito_id),
            "numero": inq_map.get(str(r.inquerito_id), "—"),
            "custo_brl": round(float(r.custo_total or 0), 2),
            "total_consultas": int(r.total_consultas),
        }
        for r in rows
    ]


@router.get("/projecao")
async def projecao_mensal(db: AsyncSession = Depends(get_db)):
    """
    Projeta o gasto Gemini até o final do mês com base no ritmo dos últimos 7 dias.
    """
    hoje = datetime.utcnow()
    inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sete_dias_atras = hoje - timedelta(days=7)

    # Gasto total do mês
    res_mes = await db.execute(
        select(func.coalesce(func.sum(ConsumoApi.custo_brl), 0))
        .where(ConsumoApi.timestamp >= inicio_mes)
    )
    gasto_mes = float(res_mes.scalar())

    # Gasto dos últimos 7 dias
    res_7d = await db.execute(
        select(func.coalesce(func.sum(ConsumoApi.custo_brl), 0))
        .where(ConsumoApi.timestamp >= sete_dias_atras)
    )
    gasto_7d = float(res_7d.scalar())

    # Dias restantes no mês
    import calendar
    _, dias_no_mes = calendar.monthrange(hoje.year, hoje.month)
    dias_passados = hoje.day
    dias_restantes = dias_no_mes - dias_passados

    # Ritmo diário (média dos últimos 7 dias)
    ritmo_diario = gasto_7d / 7 if gasto_7d > 0 else 0
    projecao = gasto_mes + (ritmo_diario * dias_restantes)

    return {
        "gasto_ate_hoje": round(gasto_mes, 2),
        "ritmo_diario_brl": round(ritmo_diario, 4),
        "dias_restantes": dias_restantes,
        "projecao_fim_mes": round(projecao, 2),
        "budget_brl": settings.BUDGET_BRL,
        "percentual_projetado": round((projecao / settings.BUDGET_BRL * 100) if settings.BUDGET_BRL > 0 else 0, 1),
        "alerta": projecao >= settings.BUDGET_ALERT_BRL,
    }
