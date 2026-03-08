"""
Escrivão AI — Task de Ingestão de Documentos
Pipeline assíncrono completo: extração → chunking → indexação vetorial → atualização PostgreSQL.
Conforme blueprint §6.1 (Document Ingestion Pipeline).
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.workers.celery_app import celery_app
from app.services.pdf_extractor import PDFExtractorService
from app.services.storage import StorageService
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

# Engine síncrono para uso dentro do Celery worker
sync_engine = create_engine(settings.DATABASE_URL_SYNC)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document(self, documento_id: str, inquerito_id: str):
    """
    Pipeline de ingestão assíncrona de um documento.

    Etapas (conforme blueprint §6.1):
    1. Download do arquivo do storage
    2. Extração de texto nativo (PyPDF2)
    3. Identificação de páginas que precisam de OCR
    4. Divisão em chunks (500-800 palavras)
    5. [FUTURO] Classificação do tipo de peça
    6. [FUTURO] Extração de entidades
    7. [FUTURO] Geração de embeddings + indexação no Qdrant
    8. [FUTURO] Resumos hierárquicos
    9. Atualização do status no PostgreSQL
    """
    from app.models.inquerito import Inquerito
    from app.models.documento import Documento
    from app.models.chunk import Chunk
    from app.core.state_machine import EstadoInquerito
    from app.models.estado_inquerito import TransicaoEstado

    logger.info(f"[INGESTÃO] Iniciando documento {documento_id} do inquérito {inquerito_id}")

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
            logger.info(f"[INGESTÃO] Baixando arquivo: {doc.storage_path}")
            storage = StorageService()

            try:
                import asyncio
                loop = asyncio.new_event_loop()
                content = loop.run_until_complete(storage.download_file(doc.storage_path))
                loop.close()
            except Exception as e:
                logger.error(f"Erro ao baixar arquivo: {e}")
                doc.status_processamento = "erro"
                db.commit()
                raise self.retry(exc=e)

            # ── 2. Extração de texto ──────────────────────────
            logger.info("[INGESTÃO] Extraindo texto do PDF")
            pdf_service = PDFExtractorService()
            extraction = pdf_service.extract_text(content)

            doc.total_paginas = extraction["total_paginas"]
            doc.texto_extraido = extraction["texto_completo"][:50000]  # Limitar para não estourar

            # Identificar páginas que precisam de OCR
            paginas_ocr = [
                p["numero"] for p in extraction["paginas"] if p["precisa_ocr"]
            ]
            if paginas_ocr:
                doc.status_ocr = "parcial"
                logger.info(f"[INGESTÃO] {len(paginas_ocr)} páginas precisam de OCR")
            else:
                doc.status_ocr = "completo"

            db.commit()

            # ── 3. Chunking ──────────────────────────────────
            logger.info("[INGESTÃO] Dividindo em chunks")
            chunks_data = pdf_service.chunk_text(
                extraction["paginas"],
                chunk_size=600,  # ~600 palavras por chunk
                overlap=100,
            )

            logger.info(f"[INGESTÃO] {len(chunks_data)} chunks gerados")

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

            # ── 5. [FUTURO] Embeddings + Qdrant ──────────────
            # TODO (Sprint 3): Gerar embeddings e indexar no Qdrant
            # qdrant = QdrantService()
            # qdrant.ensure_collection()
            # points = [
            #     {
            #         "id": str(c.id),
            #         "vector": generate_embedding(c.texto),
            #         "payload": {
            #             "inquerito_id": inquerito_id,
            #             "documento_id": documento_id,
            #             "pagina_inicial": c.pagina_inicial,
            #             "pagina_final": c.pagina_final,
            #             "tipo_documento": c.tipo_documento,
            #         }
            #     }
            #     for c in chunk_records
            # ]
            # qdrant.upsert_chunks(points)

            # ── 6. [FUTURO] Classificação de peças ────────────
            # TODO (Sprint 4): Classificar tipo de peça de cada chunk

            # ── 7. [FUTURO] Extração de entidades ─────────────
            # TODO (Sprint 4): Extrair pessoas, empresas, datas, etc.

            # ── 8. [FUTURO] Resumos hierárquicos ──────────────
            # TODO (Sprint 5): Gerar resumos por página, documento, volume e caso

            # ── 9. Atualizar status ───────────────────────────
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

                # Verificar se todos os documentos do inquérito já foram processados
                docs_pendentes = db.execute(
                    select(Documento)
                    .where(Documento.inquerito_id == uuid.UUID(inquerito_id))
                    .where(Documento.status_processamento.in_(["pendente", "processando"]))
                ).scalars().all()

                if len(docs_pendentes) == 0:
                    # Todos prontos → transitar para TRIAGEM
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

            logger.info(f"[INGESTÃO] Documento {documento_id} processado com sucesso")

            return {
                "status": "concluido",
                "documento_id": documento_id,
                "total_paginas": extraction["total_paginas"],
                "total_chunks": len(chunks_data),
                "paginas_ocr_pendente": len(paginas_ocr),
            }

    except Exception as e:
        logger.error(f"[INGESTÃO] Erro no processamento: {e}")
        raise self.retry(exc=e)
