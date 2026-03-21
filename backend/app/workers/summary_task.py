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

        # Atualizar documento sintético de análise (não bloqueia se falhar)
        try:
            generate_analise_task.delay(inquerito_id)
        except Exception as e:
            logger.warning(f"[RESUMO-TASK] Falha ao agendar análise analítica: {e}")

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


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def generate_analise_task(self, inquerito_id: str):
    """
    Cria ou atualiza o documento sintético "Análise Analítica dos Autos".
    Lê o resumo executivo já gerado no ResumoCache e persiste como Documento
    com tipo_peca="analise_analitica", visível junto das demais peças do inquérito.
    """
    logger.info(f"[ANALISE-TASK] Iniciando — inquerito={inquerito_id}")

    async def _run():
        from app.models.inquerito import Inquerito
        from app.models.documento import Documento
        from app.models.resumo_cache import ResumoCache
        from app.services.summary_service import SummaryService

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

        inq_uuid = uuid.UUID(inquerito_id)

        async with AsyncSession_() as db:
            inq = await db.get(Inquerito, inq_uuid)
            if not inq:
                logger.warning(f"[ANALISE-TASK] Inquérito não encontrado: {inquerito_id}")
                await engine.dispose()
                return {"status": "inquerito_nao_encontrado"}

            # Buscar resumo executivo do cache
            cache_result = await db.execute(
                select(ResumoCache)
                .where(ResumoCache.inquerito_id == inq_uuid)
                .where(ResumoCache.nivel == "caso")
            )
            caso_cache = cache_result.scalar_one_or_none()

            if not caso_cache:
                # Gerar caso não exista ainda
                docs_result = await db.execute(
                    select(Documento)
                    .where(Documento.inquerito_id == inq_uuid)
                    .where(Documento.status_processamento == "concluido")
                    .where(Documento.tipo_peca != "analise_analitica")
                )
                todos_docs = docs_result.scalars().all()

                if not todos_docs:
                    logger.warning(f"[ANALISE-TASK] Sem documentos indexados: {inquerito_id}")
                    await engine.dispose()
                    return {"status": "sem_documentos"}

                service = SummaryService()
                resumos = []
                for d in todos_docs:
                    r = await service.obter_resumo_documento(db, inq_uuid, d.id)
                    if r:
                        resumos.append(f"### {d.nome_arquivo}\n{r}")

                if not resumos:
                    await engine.dispose()
                    return {"status": "sem_resumos"}

                analise_texto = await service.resumir_caso(
                    db=db,
                    inquerito_id=inq_uuid,
                    numero_inquerito=inq.numero_procedimento or inquerito_id,
                    resumos_volumes=resumos,
                    forcar=True,
                )
            else:
                analise_texto = caso_cache.texto_resumo

            # Criar ou atualizar documento sintético
            doc_result = await db.execute(
                select(Documento)
                .where(Documento.inquerito_id == inq_uuid)
                .where(Documento.tipo_peca == "analise_analitica")
            )
            doc_sintetico = doc_result.scalar_one_or_none()

            if doc_sintetico:
                doc_sintetico.texto_extraido = analise_texto
            else:
                doc_sintetico = Documento(
                    inquerito_id=inq_uuid,
                    nome_arquivo="Análise Analítica dos Autos",
                    tipo_peca="analise_analitica",
                    status_processamento="sintetico",
                    status_ocr="sintetico",
                    texto_extraido=analise_texto,
                    total_paginas=1,
                )
                db.add(doc_sintetico)

            await db.commit()
            logger.info(f"[ANALISE-TASK] Documento sintético salvo — inquerito={inquerito_id}")

        await engine.dispose()
        return {"status": "concluido", "inquerito_id": inquerito_id}

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[ANALISE-TASK] Concluído — {result}")
        return result
    except Exception as e:
        logger.error(f"[ANALISE-TASK] Erro: {e}")
        raise self.retry(exc=e)
