"""
Task Celery temporária: migra embeddings do Qdrant para a coluna chunks.embedding.
Disparada via POST /api/v1/ingestao/admin/migrar-embeddings.
Pode ser removida após migração concluída.
"""

import logging
from celery import shared_task
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
BATCH_SIZE = 100


@celery_app.task(name="app.workers.migrar_embeddings_task.migrar_embeddings_task",
                 bind=True, max_retries=0, time_limit=1800)
def migrar_embeddings_task(self):
    """Migra todos os embeddings do Qdrant para chunks.embedding no PostgreSQL."""
    from qdrant_client import QdrantClient

    logger.info("[MIGRA-EMB] Iniciando migração Qdrant → pgvector")

    qdrant = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    collection = settings.QDRANT_COLLECTION

    try:
        info = qdrant.get_collection(collection)
        total_qdrant = info.points_count
        logger.info(f"[MIGRA-EMB] Collection '{collection}': {total_qdrant} pontos")
    except Exception as e:
        logger.error(f"[MIGRA-EMB] Qdrant inacessível: {e}")
        return {"erro": str(e)}

    engine = create_engine(
        settings.DATABASE_URL_SYNC,
        pool_size=1, max_overflow=0, pool_pre_ping=True,
    )

    migrados = 0
    pulados = 0
    erros = 0
    offset = None

    while True:
        results, next_offset = qdrant.scroll(
            collection_name=collection,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=False,
            with_vectors=True,
        )

        if not results:
            break

        params = []
        for point in results:
            vec = point.vector
            if not vec:
                pulados += 1
                continue
            params.append({
                "id": str(point.id),
                "vec": "[" + ",".join(str(v) for v in vec) + "]",
            })

        if params:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE chunks SET embedding = CAST(:vec AS vector) "
                            "WHERE id = CAST(:id AS uuid) AND embedding IS NULL"
                        ),
                        params,
                    )
                migrados += len(params)
                logger.info(f"[MIGRA-EMB] {migrados}/{total_qdrant} migrados")
            except Exception as e:
                logger.error(f"[MIGRA-EMB] Erro no lote: {e}")
                erros += len(params)

        if next_offset is None:
            break
        offset = next_offset

    with engine.connect() as conn:
        sem_emb = conn.execute(
            text("SELECT COUNT(*) FROM chunks WHERE embedding IS NULL")
        ).scalar()
        total_chunks = conn.execute(text("SELECT COUNT(*) FROM chunks")).scalar()

    resultado = {
        "migrados": migrados,
        "pulados": pulados,
        "erros": erros,
        "chunks_total": total_chunks,
        "chunks_sem_embedding": sem_emb,
    }
    logger.info(f"[MIGRA-EMB] CONCLUÍDO: {resultado}")
    return resultado
