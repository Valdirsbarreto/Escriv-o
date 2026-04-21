"""
Escrivão AI — API: Busca RAG
Endpoint de busca semântica nos chunks indexados no Qdrant.
Implementa o fluxo RAG do blueprint §6.6.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.inquerito import Inquerito
from app.schemas.busca import (
    BuscaRequest,
    BuscaResponse,
    ChunkResultado,
    StatusIndexacaoResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/busca", tags=["Busca RAG"])


@router.post("/", response_model=BuscaResponse)
async def busca_semantica(
    dados: BuscaRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Busca semântica nos chunks indexados de um inquérito.

    Fluxo RAG (blueprint §6.6):
    1. Recebe consulta do usuário
    2. Gera embedding da query
    3. Busca vetorial no Qdrant com filtros
    4. Retorna chunks mais relevantes com referências

    Os chunks retornados servirão como contexto para o LLM
    no copiloto e nos agentes.
    """
    # Verificar inquérito existe
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == dados.inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    # Gerar embedding da query
    try:
        from app.services.embedding_service import EmbeddingService
        embedding_service = EmbeddingService()
        query_vector = embedding_service.generate(dados.query)
    except Exception as e:
        logger.error(f"[BUSCA] Erro ao gerar embedding: {e}")
        raise HTTPException(
            status_code=503,
            detail="Serviço de embeddings indisponível. Verifique se sentence-transformers está instalado.",
        )

    # Buscar no pgvector
    try:
        from app.services.pgvector_service import PgvectorService

        results = await PgvectorService(db).search(
            query_vector=query_vector,
            limit=dados.limit,
            inquerito_id=str(dados.inquerito_id),
            tipo_documento=dados.tipo_documento,
            score_threshold=dados.score_minimo,
        )
    except Exception as e:
        logger.error(f"[BUSCA] Erro ao buscar no pgvector: {e}")
        raise HTTPException(
            status_code=503,
            detail="Serviço de busca vetorial indisponível.",
        )

    # Formatar resultados
    chunks = []
    for r in results:
        payload = r.get("payload", {})
        chunks.append(
            ChunkResultado(
                chunk_id=r["id"],
                score=round(r["score"], 4),
                texto_preview=payload.get("texto_preview", ""),
                pagina_inicial=payload.get("pagina_inicial", 0),
                pagina_final=payload.get("pagina_final", 0),
                tipo_documento=payload.get("tipo_documento", ""),
                documento_id=payload.get("documento_id", ""),
                inquerito_id=payload.get("inquerito_id", ""),
            )
        )

    return BuscaResponse(
        query=dados.query,
        total_resultados=len(chunks),
        resultados=chunks,
    )


@router.get("/status/{inquerito_id}", response_model=StatusIndexacaoResponse)
async def status_indexacao(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retorna o status da indexação de um inquérito no Qdrant."""
    # Verificar inquérito
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    try:
        from app.services.pgvector_service import PgvectorService
        svc = PgvectorService(db)
        total_chunks = await svc.count_by_inquerito(str(inquerito_id))
        colecao_info = await svc.get_collection_info()
    except Exception:
        total_chunks = 0
        colecao_info = {"status": "indisponível"}

    return StatusIndexacaoResponse(
        inquerito_id=inquerito_id,
        total_chunks_indexados=total_chunks,
        colecao_info=colecao_info,
    )
