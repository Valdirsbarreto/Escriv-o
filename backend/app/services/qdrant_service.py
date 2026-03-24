"""
Escrivão AI — Serviço Qdrant
Wrapper para o cliente Qdrant: criação de coleção, upsert e busca vetorial/RAG.
"""

import logging
from typing import List, Optional, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class QdrantService:
    """Gerencia operações no banco vetorial Qdrant."""

    VECTOR_SIZE = 384  # all-MiniLM-L6-v2

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            check_version=False,
        )
        self.collection_name = settings.QDRANT_COLLECTION

    def ensure_collection(self, vector_size: int = None):
        """Cria a coleção se não existir."""
        size = vector_size or self.VECTOR_SIZE
        collections = self.client.get_collections().collections
        names = [c.name for c in collections]

        if self.collection_name not in names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                f"[QDRANT] Coleção '{self.collection_name}' criada (dims={size})"
            )
        else:
            logger.info(
                f"[QDRANT] Coleção '{self.collection_name}' já existe"
            )

    def upsert_chunks(
        self,
        points: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> int:
        """
        Insere ou atualiza pontos no Qdrant em lotes.

        Cada ponto deve conter:
        - id: str (UUID)
        - vector: List[float]
        - payload: dict com metadados (inquerito_id, documento_id, etc.)

        Returns: total de pontos inseridos
        """
        total = 0

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            qdrant_points = [
                PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p.get("payload", {}),
                )
                for p in batch
            ]

            self.client.upsert(
                collection_name=self.collection_name,
                points=qdrant_points,
            )
            total += len(qdrant_points)
            logger.info(f"[QDRANT] Batch {i // batch_size + 1}: {len(qdrant_points)} pontos inseridos")

        return total

    def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        inquerito_id: Optional[str] = None,
        tipo_documento: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Busca vetorial com filtros opcionais por metadados.
        Retorna chunks mais relevantes para RAG.
        """
        filters = []
        if inquerito_id:
            filters.append(
                FieldCondition(
                    key="inquerito_id",
                    match=MatchValue(value=inquerito_id),
                )
            )
        if tipo_documento:
            filters.append(
                FieldCondition(
                    key="tipo_documento",
                    match=MatchValue(value=tipo_documento),
                )
            )

        search_filter = Filter(must=filters) if filters else None

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=search_filter,
            with_payload=True,
            score_threshold=score_threshold,
        )

        return [
            {
                "id": str(r.id),
                "score": r.score,
                "payload": r.payload,
            }
            for r in results
        ]

    def count_by_inquerito(self, inquerito_id: str) -> int:
        """Conta pontos indexados para um inquérito."""
        try:
            result = self.client.count(
                collection_name=self.collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="inquerito_id",
                            match=MatchValue(value=inquerito_id),
                        )
                    ]
                ),
            )
            return result.count
        except Exception:
            return 0

    def delete_by_inquerito(self, inquerito_id: str) -> None:
        """Remove todos os pontos de um inquérito."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="inquerito_id",
                        match=MatchValue(value=inquerito_id),
                    )
                ]
            ),
        )
        logger.info(f"[QDRANT] Pontos removidos para inquérito {inquerito_id}")

    def get_collection_info(self) -> Dict[str, Any]:
        """Retorna informações da coleção."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "nome": self.collection_name,
                "total_pontos": info.points_count,
                "vetores_indexados": info.indexed_vectors_count,
                "status": info.status.value,
            }
        except Exception as e:
            return {"erro": str(e)}
