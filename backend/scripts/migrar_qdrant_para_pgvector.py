"""
Script de migração: Qdrant → pgvector
Lê todos os embeddings do Qdrant e grava na coluna chunks.embedding do PostgreSQL.

Uso (no Railway shell ou localmente com variáveis de ambiente corretas):
    python -m scripts.migrar_qdrant_para_pgvector

O script é idempotente: pula chunks que já têm embedding na coluna.
"""

import os
import sys
import logging
from pathlib import Path

# Garante que o diretório backend está no path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # pontos por lote do Qdrant scroll


def main():
    from app.core.config import settings
    from qdrant_client import QdrantClient
    from sqlalchemy import create_engine, text

    # ── Conexão Qdrant ────────────────────────────────────────────────────────
    logger.info(f"Conectando ao Qdrant: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    qdrant = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    collection = settings.QDRANT_COLLECTION

    try:
        info = qdrant.get_collection(collection)
        total_qdrant = info.points_count
        logger.info(f"Collection '{collection}': {total_qdrant} pontos")
    except Exception as e:
        logger.error(f"Não foi possível conectar ao Qdrant: {e}")
        sys.exit(1)

    # ── Conexão PostgreSQL ────────────────────────────────────────────────────
    logger.info("Conectando ao PostgreSQL...")
    engine = create_engine(
        settings.DATABASE_URL_SYNC,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )

    migrados = 0
    pulados = 0
    erros = 0
    offset = None

    logger.info("Iniciando migração em lotes de %d...", BATCH_SIZE)

    while True:
        # Scroll no Qdrant com vetores
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
            vec_str = "[" + ",".join(str(v) for v in vec) + "]"
            params.append({"id": str(point.id), "vec": vec_str})

        if params:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE chunks "
                            "SET embedding = :vec::vector "
                            "WHERE id = :id::uuid AND embedding IS NULL"
                        ),
                        params,
                    )
                migrados += len(params)
                logger.info(f"  Migrados: {migrados} / {total_qdrant} (lote de {len(params)})")
            except Exception as e:
                logger.error(f"Erro ao gravar lote: {e}")
                erros += len(params)

        if next_offset is None:
            break
        offset = next_offset

    logger.info("=" * 60)
    logger.info(f"CONCLUÍDO: {migrados} migrados | {pulados} sem vetor | {erros} erros")

    # Verifica quantos chunks ainda não têm embedding
    with engine.connect() as conn:
        sem_emb = conn.execute(
            text("SELECT COUNT(*) FROM chunks WHERE embedding IS NULL")
        ).scalar()
        total_chunks = conn.execute(text("SELECT COUNT(*) FROM chunks")).scalar()
        logger.info(f"PostgreSQL: {total_chunks - sem_emb}/{total_chunks} chunks com embedding")

    if sem_emb > 0:
        logger.warning(
            f"{sem_emb} chunks ainda sem embedding — podem ser documentos não indexados no Qdrant. "
            "Re-ingerir esses documentos irá gerar os embeddings automaticamente."
        )


if __name__ == "__main__":
    main()
