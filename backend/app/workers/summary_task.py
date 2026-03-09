"""
Escrivão AI — Task Celery: Geração de Resumos Hierárquicos
Executada após ingestão de documento para gerar e cachear resumos por nível.
Conforme blueprint §6.4 (Resumos Hierárquicos).
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def generate_summaries_task(self, inquerito_id: str, documento_id: str):
    """
    Task Celery que gera os resumos hierárquicos de um documento.

    Fluxo:
    1. Resumo do Documento (texto completo → LLM Econômico)
    2. Resumo do Volume correspondente (consolida resumos de todos os docs do volume)
    3. Resumo do Caso (consolida resumos de todos os volumes)
    """
    logger.info(f"[RESUMO-TASK] Iniciando resumos — doc={documento_id}")

    async def _run():
        from app.models.documento import Documento
        from app.models.volume import Volume
        from app.models.inquerito import Inquerito
        from app.models.resumo_cache import ResumoCache
        from app.services.summary_service import SummaryService

        # Engine async dedicado pro worker
        async_url = _encode_password_in_url(settings.DATABASE_URL)

        import ssl
        connect_args = {}
        if "supabase" in async_url or "localhost" not in async_url:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx

        engine = create_async_engine(async_url, connect_args=connect_args if connect_args else {})
        AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        service = SummaryService()

        doc_uuid = uuid.UUID(documento_id)
        inq_uuid = uuid.UUID(inquerito_id)

        async with AsyncSession_() as db:
            # ── 1. Resumo do documento ─────────────────────────
            doc = await db.get(Documento, doc_uuid)
            if not doc or not doc.texto_extraido:
                logger.warning(f"[RESUMO-TASK] Documento sem texto: {documento_id}")
                return {"status": "sem_texto"}

            await service.resumir_documento(
                db=db,
                inquerito_id=inq_uuid,
                documento_id=doc_uuid,
                texto=doc.texto_extraido,
                nome_arquivo=doc.nome_arquivo,
                tipo_peca=doc.tipo_peca or "outro",
            )

            # ── 2. Resumo do volume ────────────────────────────
            # Buscar todos os documentos do mesmo inquérito para consolidar
            result = await db.execute(
                select(Documento)
                .where(Documento.inquerito_id == inq_uuid)
                .where(Documento.status_processamento == "concluido")
            )
            todos_docs = result.scalars().all()

            # Buscar (ou gerar) resumo de cada documento
            resumos_docs = []
            for d in todos_docs:
                r_doc = await service.obter_resumo_documento(db, inq_uuid, d.id)
                if r_doc:
                    resumos_docs.append(f"### {d.nome_arquivo}\n{r_doc}")

            if resumos_docs:
                # Volume 1 por padrão se não houver separação por volumes
                # (suporte multi-volume pode ser adicionado depois)
                resumo_volume = await service.resumir_volume(
                    db=db,
                    inquerito_id=inq_uuid,
                    volume_id=inq_uuid,  # Usa o inquerito_id como volume_id único por ora
                    numero_volume=1,
                    resumos_documentos=resumos_docs,
                    forcar=True,  # Regerar pois um novo doc foi adicionado
                )

            # ── 3. Resumo executivo do caso ────────────────────
            inq = await db.get(Inquerito, inq_uuid)
            if inq:
                resumo_volume_final = await service.obter_resumo_documento(
                    db, inq_uuid, inq_uuid  # buscar volume
                ) or (resumos_docs[0] if resumos_docs else "")
                
                # Buscar resumo de volume que geramos no step anterior
                volume_cache_result = await db.execute(
                    select(ResumoCache)
                    .where(ResumoCache.inquerito_id == inq_uuid)
                    .where(ResumoCache.nivel == "volume")
                )
                vol_cache = volume_cache_result.scalar_one_or_none()
                resumo_vol_texto = vol_cache.texto_resumo if vol_cache else "\n".join(resumos_docs[:5])

                await service.resumir_caso(
                    db=db,
                    inquerito_id=inq_uuid,
                    numero_inquerito=inq.numero_procedimento or str(inquerito_id),
                    resumos_volumes=[resumo_vol_texto],
                    forcar=True,  # Regerar sempre que nova doc é adicionada
                )

        await engine.dispose()
        return {"status": "concluido", "documento_id": documento_id}

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[RESUMO-TASK] Concluído — {result}")
        return result
    except Exception as e:
        logger.error(f"[RESUMO-TASK] Erro: {e}")
        raise self.retry(exc=e)
