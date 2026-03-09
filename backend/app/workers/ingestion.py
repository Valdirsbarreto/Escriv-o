"""
Escrivão AI — Task de Ingestão de Documentos (Sprint 2)
Pipeline assíncrono completo: extração → OCR seletivo → chunking → embeddings → Qdrant.
Conforme blueprint §6.1 (Document Ingestion Pipeline).
"""

import logging
import time
import uuid
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.workers.celery_app import celery_app
from app.services.pdf_extractor import PDFExtractorService
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

# Engine síncrono para uso dentro do worker Celery
sync_engine = create_engine(settings.DATABASE_URL_SYNC)


def _log_etapa(db: Session, documento_id: str, inquerito_id: str,
               etapa: str, status: str, detalhes: str = None,
               duracao_ms: int = None, dados_extras: dict = None):
    """Registra uma etapa no log de ingestão."""
    from app.models.log_ingestao import LogIngestao
    log = LogIngestao(
        documento_id=uuid.UUID(documento_id),
        inquerito_id=uuid.UUID(inquerito_id),
        etapa=etapa,
        status=status,
        detalhes=detalhes,
        duracao_ms=duracao_ms,
        dados_extras=dados_extras,
    )
    db.add(log)
    db.commit()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document(self, documento_id: str, inquerito_id: str):
    """
    Pipeline de ingestão assíncrona de um documento.

    Etapas (conforme blueprint §6.1):
    1. Download do arquivo do storage
    2. Extração de texto nativo (pypdf)
    3. OCR seletivo nas páginas sem texto confiável
    4. Divisão em chunks (500-800 palavras)
    5. Geração de embeddings (sentence-transformers)
    6. Indexação no Qdrant com metadados
    7. [FUTURO Sprint 4] Classificação do tipo de peça
    8. [FUTURO Sprint 4] Extração de entidades
    9. [FUTURO Sprint 5] Resumos hierárquicos
    10. Atualização do status no PostgreSQL
    """
    from app.models.inquerito import Inquerito
    from app.models.documento import Documento
    from app.models.chunk import Chunk
    from app.core.state_machine import EstadoInquerito
    from app.models.estado_inquerito import TransicaoEstado

    logger.info(f"[INGESTÃO] Iniciando documento {documento_id} do inquérito {inquerito_id}")
    pipeline_start = time.time()

    try:
        with Session(sync_engine) as db:
            # ── Buscar documento ──────────────────────────────
            doc = db.execute(
                select(Documento).where(Documento.id == uuid.UUID(documento_id))
            ).scalar_one_or_none()

            if not doc:
                logger.error(f"Documento {documento_id} não encontrado")
                return {"status": "erro", "mensagem": "Documento não encontrado"}

            doc.status_processamento = "processando"
            db.commit()

            # ── 1. Download do arquivo ────────────────────────
            t0 = time.time()
            logger.info(f"[INGESTÃO] Baixando arquivo: {doc.storage_path}")
            storage = StorageService()

            try:
                import asyncio
                loop = asyncio.new_event_loop()
                content = loop.run_until_complete(storage.download_file(doc.storage_path))
                loop.close()
            except Exception as e:
                _log_etapa(db, documento_id, inquerito_id, "download", "erro",
                           detalhes=str(e))
                logger.error(f"Erro ao baixar arquivo: {e}")
                doc.status_processamento = "erro"
                db.commit()
                raise self.retry(exc=e)

            _log_etapa(db, documento_id, inquerito_id, "download", "concluido",
                       duracao_ms=int((time.time() - t0) * 1000),
                       dados_extras={"tamanho_bytes": len(content)})

            # ── 2. Extração de texto + OCR seletivo ───────────
            t0 = time.time()
            logger.info("[INGESTÃO] Extraindo texto do PDF (com OCR seletivo)")
            pdf_service = PDFExtractorService()
            extraction = pdf_service.extract_with_ocr(content)

            doc.total_paginas = extraction["total_paginas"]
            doc.texto_extraido = extraction["texto_completo"][:100000]

            paginas_ocr = [
                p["numero"] for p in extraction["paginas"]
                if p.get("origem") == "ocr"
            ]
            paginas_pendentes = [
                p["numero"] for p in extraction["paginas"]
                if p.get("precisa_ocr", False)
            ]

            if paginas_pendentes:
                doc.status_ocr = "parcial"
            elif paginas_ocr:
                doc.status_ocr = "completo_com_ocr"
            else:
                doc.status_ocr = "completo"

            db.commit()

            _log_etapa(db, documento_id, inquerito_id, "extracao", "concluido",
                       duracao_ms=int((time.time() - t0) * 1000),
                       dados_extras={
                           "total_paginas": extraction["total_paginas"],
                           "paginas_ocr": len(paginas_ocr),
                           "paginas_pendentes": len(paginas_pendentes),
                       })

            # ── 3. Chunking ──────────────────────────────────
            t0 = time.time()
            logger.info("[INGESTÃO] Dividindo em chunks")
            chunks_data = pdf_service.chunk_text(
                extraction["paginas"],
                chunk_size=600,
                overlap=100,
            )

            logger.info(f"[INGESTÃO] {len(chunks_data)} chunks gerados")

            _log_etapa(db, documento_id, inquerito_id, "chunking", "concluido",
                       duracao_ms=int((time.time() - t0) * 1000),
                       dados_extras={"total_chunks": len(chunks_data)})

            # ── 4. Salvar chunks no PostgreSQL ────────────────
            chunk_records = []
            for chunk_data in chunks_data:
                chunk = Chunk(
                    inquerito_id=uuid.UUID(inquerito_id),
                    documento_id=uuid.UUID(documento_id),
                    pagina_inicial=chunk_data["pagina_inicial"],
                    pagina_final=chunk_data["pagina_final"],
                    texto=chunk_data["texto"],
                )
                db.add(chunk)
                chunk_records.append(chunk)

            db.commit()

            # Refresh para obter IDs
            for chunk in chunk_records:
                db.refresh(chunk)

            # ── 5. Embeddings ─────────────────────────────────
            t0 = time.time()
            logger.info(f"[INGESTÃO] Gerando embeddings para {len(chunk_records)} chunks")

            try:
                from app.services.embedding_service import EmbeddingService

                embedding_service = EmbeddingService()
                textos = [c.texto for c in chunk_records]
                embeddings = embedding_service.generate_batch(textos, batch_size=64)

                for chunk, embedding in zip(chunk_records, embeddings):
                    chunk.embedding_model = "all-MiniLM-L6-v2"

                db.commit()

                _log_etapa(db, documento_id, inquerito_id, "embedding", "concluido",
                           duracao_ms=int((time.time() - t0) * 1000),
                           dados_extras={
                               "total_embeddings": len(embeddings),
                               "modelo": "all-MiniLM-L6-v2",
                               "dimensoes": 384,
                           })

            except Exception as e:
                logger.warning(f"[INGESTÃO] Embeddings falharam: {e}")
                _log_etapa(db, documento_id, inquerito_id, "embedding", "erro",
                           detalhes=str(e),
                           duracao_ms=int((time.time() - t0) * 1000))
                embeddings = None

            # ── 6. Indexação no Qdrant ────────────────────────
            if embeddings:
                t0 = time.time()
                logger.info("[INGESTÃO] Indexando no Qdrant")

                try:
                    from app.services.qdrant_service import QdrantService

                    qdrant = QdrantService()
                    qdrant.ensure_collection(vector_size=384)

                    points = [
                        {
                            "id": str(chunk.id),
                            "vector": embedding,
                            "payload": {
                                "inquerito_id": inquerito_id,
                                "documento_id": documento_id,
                                "chunk_id": str(chunk.id),
                                "pagina_inicial": chunk.pagina_inicial,
                                "pagina_final": chunk.pagina_final,
                                "tipo_documento": chunk.tipo_documento or "",
                                "texto_preview": chunk.texto[:500],
                            },
                        }
                        for chunk, embedding in zip(chunk_records, embeddings)
                    ]

                    total_indexado = qdrant.upsert_chunks(points)

                    # Atualizar qdrant_point_id nos chunks
                    for chunk in chunk_records:
                        chunk.qdrant_point_id = str(chunk.id)
                    db.commit()

                    _log_etapa(db, documento_id, inquerito_id, "indexacao", "concluido",
                               duracao_ms=int((time.time() - t0) * 1000),
                               dados_extras={"total_indexado": total_indexado})

                except Exception as e:
                    logger.warning(f"[INGESTÃO] Indexação Qdrant falhou: {e}")
                    _log_etapa(db, documento_id, inquerito_id, "indexacao", "erro",
                               detalhes=str(e),
                               duracao_ms=int((time.time() - t0) * 1000))

            # ── 7. [FUTURO] Classificação de peças ────────────
            # TODO (Sprint 4): Classificar tipo de peça de cada chunk

            # ── 8. [FUTURO] Extração de entidades ─────────────
            # TODO (Sprint 4): Extrair pessoas, empresas, datas, etc.

            # ── 9. [FUTURO] Resumos hierárquicos ──────────────
            # TODO (Sprint 5): Gerar resumos por página, documento, volume, caso

            # ── 10. Atualizar status ──────────────────────────
            doc.status_processamento = "concluido"
            db.commit()

            # Atualizar inquérito
            inquerito = db.execute(
                select(Inquerito).where(Inquerito.id == uuid.UUID(inquerito_id))
            ).scalar_one_or_none()

            if inquerito:
                inquerito.total_paginas += extraction["total_paginas"]

                # Ativar modo grande se ultrapassar 1500 páginas
                if inquerito.total_paginas > 1500:
                    inquerito.modo_grande = True
                    logger.info("[INGESTÃO] Modo inquérito grande ativado (>1500 páginas)")

                # Verificar se todos os documentos foram processados
                docs_pendentes = db.execute(
                    select(Documento)
                    .where(Documento.inquerito_id == uuid.UUID(inquerito_id))
                    .where(Documento.status_processamento.in_(["pendente", "processando"]))
                ).scalars().all()

                if len(docs_pendentes) == 0:
                    if inquerito.estado_atual == EstadoInquerito.INDEXANDO.value:
                        estado_anterior = inquerito.estado_atual
                        inquerito.estado_atual = EstadoInquerito.TRIAGEM.value
                        transicao = TransicaoEstado(
                            inquerito_id=inquerito.id,
                            estado_anterior=estado_anterior,
                            estado_novo=EstadoInquerito.TRIAGEM.value,
                            motivo="Indexação completa de todos os documentos",
                        )
                        db.add(transicao)
                        logger.info("[INGESTÃO] Inquérito transitou para TRIAGEM")

                db.commit()

            duracao_total = int((time.time() - pipeline_start) * 1000)
            _log_etapa(db, documento_id, inquerito_id, "pipeline_completo", "concluido",
                       duracao_ms=duracao_total,
                       dados_extras={
                           "total_paginas": extraction["total_paginas"],
                           "total_chunks": len(chunks_data),
                           "paginas_ocr": len(paginas_ocr),
                           "embeddings_gerados": len(embeddings) if embeddings else 0,
                       })

            logger.info(
                f"[INGESTÃO] Documento {documento_id} processado em {duracao_total}ms — "
                f"{extraction['total_paginas']} págs, {len(chunks_data)} chunks"
            )

            return {
                "status": "concluido",
                "documento_id": documento_id,
                "total_paginas": extraction["total_paginas"],
                "total_chunks": len(chunks_data),
                "paginas_ocr": len(paginas_ocr),
                "embeddings_gerados": len(embeddings) if embeddings else 0,
                "duracao_ms": duracao_total,
            }

    except Exception as e:
        logger.error(f"[INGESTÃO] Erro no processamento: {e}")
        try:
            with Session(sync_engine) as db:
                _log_etapa(db, documento_id, inquerito_id, "pipeline_completo", "erro",
                           detalhes=str(e))
        except Exception:
            pass
        raise self.retry(exc=e)
