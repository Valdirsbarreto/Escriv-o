"""
Escrivão AI — Task Celery: Vigilância Periódica
Verifica proativamente a saúde do sistema a cada 45 minutos e alerta o Comissário.

Verificações:
  1. Heartbeat do Celery Beat (Redis stamp)
  2. Documentos presos em processamento > 45 min
  3. Inquéritos com todos docs concluídos mas sem relatório > 6h
  4. Budget LLM mensal (≥80% e ≥100% do limite)
  5. Supabase egress mensal (≥80% do limite gratuito)

beat_heartbeat_stamp_task: grava timestamp no Redis a cada 5 min (prova que o Beat está vivo).
"""

import asyncio
import logging
from datetime import datetime, timedelta

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=0)
def beat_heartbeat_stamp_task(self):
    """Grava timestamp no Redis para provar que o Celery Beat está vivo."""
    try:
        from app.core.config import settings
        import redis as redis_lib

        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        r.set("escrivao:beat:heartbeat", datetime.utcnow().isoformat(), ex=3600)
        logger.debug("[VIGILANCIA] Heartbeat stamp gravado")
    except Exception as e:
        logger.warning(f"[VIGILANCIA] Falha ao gravar heartbeat stamp: {e}")


@celery_app.task(bind=True, max_retries=0)
def vigilancia_periodica_task(self):
    """Executa 5 verificações de saúde do sistema e envia alertas se necessário."""
    logger.info("[VIGILANCIA] ── Iniciando ciclo de vigilância ──")
    asyncio.run(_run_vigilancia())
    logger.info("[VIGILANCIA] ── Ciclo concluído ──")


async def _run_vigilancia():
    from app.services.alerta_service import (
        enviar_alerta_sync,
        msg_heartbeat_ausente,
        msg_doc_preso,
        msg_inquerito_sem_relatorio,
        msg_budget_alerta,
        msg_budget_critico,
        msg_egress_supabase,
    )
    from app.core.config import settings

    agora = datetime.utcnow()

    # ── 1. Heartbeat do Celery Beat ───────────────────────────────────────────
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        stamp = r.get("escrivao:beat:heartbeat")
        if stamp:
            stamp_dt = datetime.fromisoformat(stamp)
            minutos_sem_beat = int((agora - stamp_dt).total_seconds() / 60)
            if minutos_sem_beat > 10:
                titulo, mensagem, mensagem_html = msg_heartbeat_ausente(minutos_sem_beat)
                enviar_alerta_sync("heartbeat_ausente", "critico", titulo, mensagem, mensagem_html)
        else:
            # Stamp nunca gravado ou expirou (TTL 1h) — Beat ausente por muito tempo
            titulo, mensagem, mensagem_html = msg_heartbeat_ausente(60)
            enviar_alerta_sync("heartbeat_ausente", "critico", titulo, mensagem, mensagem_html)
    except Exception as e:
        logger.warning(f"[VIGILANCIA] Erro na verificação de heartbeat: {e}")

    # ── 2. Documentos presos em processamento ─────────────────────────────────
    try:
        import re
        from sqlalchemy import create_engine, and_, select
        from sqlalchemy.orm import sessionmaker
        from app.core.database import _encode_password_in_url
        from app.models.documento import Documento
        from app.models.inquerito import Inquerito

        engine = create_engine(
            _encode_password_in_url(settings.DATABASE_URL_SYNC),
            pool_size=1, max_overflow=0, pool_pre_ping=True, pool_recycle=300
        )
        Session = sessionmaker(bind=engine)
        limite_45 = agora - timedelta(minutes=45)
        limite_6h = agora - timedelta(hours=6)

        with Session() as db:
            # Docs presos
            docs_presos = db.execute(
                select(Documento, Inquerito.numero)
                .join(Inquerito, Documento.inquerito_id == Inquerito.id)
                .where(
                    and_(
                        Documento.status_processamento == "processando",
                        Documento.created_at < limite_45,
                    )
                )
                .limit(3)
            ).all()

            for doc, inq_numero in docs_presos:
                minutos = int((agora - doc.created_at).total_seconds() / 60)
                titulo, mensagem, mensagem_html = msg_doc_preso(
                    inq_numero or "?", doc.nome_arquivo or str(doc.id)[:16], minutos, str(doc.id)
                )
                enviar_alerta_sync("doc_stuck", "alerta", titulo, mensagem, mensagem_html, identificador=str(doc.id))

            # IPs sem relatório > 6h
            from sqlalchemy import exists, not_
            from app.models.documento_gerado import DocumentoGerado

            inqs_sem_relatorio = db.execute(
                select(Inquerito.id, Inquerito.numero, Inquerito.updated_at)
                .where(
                    and_(
                        Inquerito.updated_at < limite_6h,
                        exists(
                            select(Documento.id).where(
                                and_(
                                    Documento.inquerito_id == Inquerito.id,
                                    Documento.status_processamento == "concluido",
                                )
                            )
                        ),
                        not_(
                            exists(
                                select(Documento.id).where(
                                    and_(
                                        Documento.inquerito_id == Inquerito.id,
                                        Documento.status_processamento.in_(["pendente", "processando"]),
                                    )
                                )
                            )
                        ),
                        not_(
                            exists(
                                select(DocumentoGerado.id).where(
                                    and_(
                                        DocumentoGerado.inquerito_id == Inquerito.id,
                                        DocumentoGerado.tipo == "relatorio_inicial",
                                    )
                                )
                            )
                        ),
                    )
                )
                .limit(3)
            ).all()

            for inq_id, inq_numero, inq_updated in inqs_sem_relatorio:
                horas = int((agora - inq_updated).total_seconds() / 3600)
                titulo, mensagem, mensagem_html = msg_inquerito_sem_relatorio(
                    inq_numero or "?", horas, str(inq_id)
                )
                enviar_alerta_sync(
                    "inquerito_sem_relatorio", "alerta", titulo, mensagem, mensagem_html,
                    identificador=str(inq_id)
                )

            # Budget LLM
            from sqlalchemy import func, text
            from app.models.consumo_api import ConsumoApi

            inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            gasto_result = db.execute(
                select(func.sum(ConsumoApi.custo_brl)).where(ConsumoApi.timestamp >= inicio_mes)
            )
            gasto_brl = float(gasto_result.scalar() or 0)
            limite_brl = float(settings.BUDGET_BRL or 0)
            limite_alerta_brl = float(settings.BUDGET_ALERT_BRL or limite_brl * 0.8)

            if limite_brl > 0:
                pct = gasto_brl / limite_brl * 100
                mes_str = agora.strftime("%Y-%m")
                if pct >= 100:
                    titulo, mensagem, mensagem_html = msg_budget_critico(gasto_brl, limite_brl)
                    enviar_alerta_sync("budget_critico", "critico", titulo, mensagem, mensagem_html, identificador=mes_str)
                elif gasto_brl >= limite_alerta_brl:
                    titulo, mensagem, mensagem_html = msg_budget_alerta(gasto_brl, limite_brl, pct)
                    enviar_alerta_sync("budget_alerta", "alerta", titulo, mensagem, mensagem_html, identificador=mes_str)

        engine.dispose()
    except Exception as e:
        logger.error(f"[VIGILANCIA] Erro nas verificações de banco: {e}")

    # ── 5. Supabase egress ────────────────────────────────────────────────────
    try:
        import httpx
        token = settings.SUPABASE_MANAGEMENT_TOKEN
        supabase_url = settings.SUPABASE_URL or ""
        ref = supabase_url.replace("https://", "").split(".")[0] if supabase_url else None

        if token and ref and len(ref) >= 5:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://api.supabase.com/v1/projects/{ref}/usage",
                    headers={"Authorization": f"Bearer {token}"},
                )
            if resp.status_code == 200:
                data = resp.json()
                egress_bytes = int(data.get("egress_bytes") or 0)
                limite_bytes = 5 * 1024 ** 3  # 5 GB gratuito
                MB = 1024 ** 2
                egress_mb = egress_bytes / MB
                limite_mb = limite_bytes / MB
                pct = egress_mb / limite_mb * 100

                if pct >= 80:
                    mes_str = agora.strftime("%Y-%m")
                    titulo, mensagem, mensagem_html = msg_egress_supabase(egress_mb, limite_mb, pct)
                    enviar_alerta_sync(
                        "egress_supabase", "alerta", titulo, mensagem, mensagem_html,
                        identificador=mes_str
                    )
    except Exception as e:
        logger.warning(f"[VIGILANCIA] Erro na verificação Supabase egress: {e}")
