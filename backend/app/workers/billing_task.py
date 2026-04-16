"""
Escrivão AI — Billing Task
Task Celery beat que roda 1x/dia (00:30 UTC) e coleta custos de todos
os provedores externos, fazendo UPSERT em custos_externos.

Regras:
  - Entradas com source='manual' são preservadas (não sobrescritas)
  - Falha de um provedor não interrompe os demais
  - Grava source, confidence e raw_payload para auditoria
"""

import asyncio
import logging
from datetime import datetime

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.billing_task.coletar_custos_externos_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def coletar_custos_externos_task(self):
    """Coleta custos de Vercel, Railway, Supabase e Serper e salva em custos_externos."""
    try:
        asyncio.run(_run_coleta())
    except Exception as exc:
        logger.error(f"[BILLING] Falha na task de billing: {exc}", exc_info=True)
        raise self.retry(exc=exc)


async def _run_coleta():
    from decimal import Decimal
    from sqlalchemy import select
    from app.core.database import async_session
    from app.core.config import settings
    from app.models.custo_externo import CustoExterno
    from app.services.billing_collectors import (
        coletar_vercel,
        coletar_railway,
        coletar_supabase,
        coletar_serper,
    )

    mes = datetime.utcnow().strftime("%Y-%m")
    cotacao = settings.COTACAO_DOLAR

    logger.info(f"[BILLING] Iniciando coleta de custos para {mes}")

    async with async_session() as db:
        # Serper precisa da sessão para ler usage_events
        collectors = {
            "vercel":   lambda: coletar_vercel(mes, cotacao),
            "railway":  lambda: coletar_railway(mes, cotacao),
            "supabase": lambda: coletar_supabase(mes, cotacao),
            "serper":   lambda: coletar_serper(mes, cotacao, db),
        }

        for servico, coletor in collectors.items():
            try:
                resultado = await coletor()

                if resultado is None:
                    logger.debug(f"[BILLING] {servico} — sem dados disponíveis, skip")
                    continue

                # Verificar se já existe entrada manual — preservar
                res = await db.execute(
                    select(CustoExterno)
                    .where(CustoExterno.servico == servico)
                    .where(CustoExterno.mes == mes)
                )
                registro = res.scalar_one_or_none()

                if registro and registro.source == "manual":
                    logger.info(f"[BILLING] {servico}/{mes} — entrada manual preservada, skip")
                    continue

                if registro:
                    registro.custo_usd   = resultado.custo_usd
                    registro.custo_brl   = resultado.custo_brl
                    registro.source      = resultado.source
                    registro.confidence  = resultado.confidence
                    registro.raw_payload = resultado.raw_payload
                    registro.observacao  = resultado.observacao
                    registro.updated_at  = datetime.utcnow()
                    logger.info(f"[BILLING] {servico}/{mes} — atualizado R$ {resultado.custo_brl} ({resultado.source})")
                else:
                    db.add(CustoExterno(
                        servico=servico,
                        mes=mes,
                        custo_usd=resultado.custo_usd,
                        custo_brl=resultado.custo_brl,
                        source=resultado.source,
                        confidence=resultado.confidence,
                        raw_payload=resultado.raw_payload,
                        observacao=resultado.observacao,
                    ))
                    logger.info(f"[BILLING] {servico}/{mes} — criado R$ {resultado.custo_brl} ({resultado.source})")

            except Exception as e:
                logger.warning(f"[BILLING] Erro ao coletar {servico}: {e}", exc_info=True)
                # Continua para o próximo provedor

        await db.commit()
        logger.info(f"[BILLING] Coleta concluída para {mes}")
