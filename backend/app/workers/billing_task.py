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
import ssl
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _make_engine():
    """Cria engine async com NullPool — padrão obrigatório para workers Celery."""
    url = _encode_password_in_url(settings.DATABASE_URL)
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    connect_args = {"statement_cache_size": 0}
    if "supabase" in url or "localhost" not in url:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx

    return create_async_engine(url, connect_args=connect_args, poolclass=NullPool)


@celery_app.task(
    name="app.workers.billing_task.coletar_custos_externos_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def coletar_custos_externos_task(self):
    """Coleta custos de Vercel, Railway, Supabase e Serper e salva em custos_externos."""

    async def _run():
        from sqlalchemy import select
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

        engine = _make_engine()
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        try:
            async with Session() as db:
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
                            logger.debug(f"[BILLING] {servico} — sem dados, skip")
                            continue

                        res = await db.execute(
                            select(CustoExterno)
                            .where(CustoExterno.servico == servico)
                            .where(CustoExterno.mes == mes)
                        )
                        registro = res.scalar_one_or_none()

                        if registro and registro.source == "manual":
                            logger.info(f"[BILLING] {servico}/{mes} — entrada manual preservada")
                            continue

                        if registro:
                            registro.custo_usd   = resultado.custo_usd
                            registro.custo_brl   = resultado.custo_brl
                            registro.source      = resultado.source
                            registro.confidence  = resultado.confidence
                            registro.raw_payload = resultado.raw_payload
                            registro.observacao  = resultado.observacao
                            registro.updated_at  = datetime.utcnow()
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

                        logger.info(
                            f"[BILLING] {servico}/{mes} — R$ {resultado.custo_brl} "
                            f"({resultado.source}/{resultado.confidence})"
                        )

                    except Exception as e:
                        logger.warning(f"[BILLING] Erro ao coletar {servico}: {e}", exc_info=True)

                await db.commit()
                logger.info(f"[BILLING] Coleta concluída para {mes}")
        finally:
            await engine.dispose()

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()
    except Exception as exc:
        logger.error(f"[BILLING] Falha na task: {exc}", exc_info=True)
        raise self.retry(exc=exc)
