"""
Escrivão AI — Serviço Qdrant
Wrapper para o cliente Qdrant: criação de coleção, upsert e busca vetorial.
"""

from typing import List, Optional, Dict, Any
from uuid import uuid4

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


class QdrantService:
    """Gerencia operações no banco vetorial Qdrant."""

    VECTOR_SIZE = 1536  # Tamanho padrão para embeddings OpenAI

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
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

    def upsert_chunks(
        self,
        points: List[Dict[str, Any]],
    ) -> None:
        """
        Insere ou atualiza pontos no Qdrant.

        Cada ponto deve conter:
        - id: str (UUID)
        - vector: List[float]
        - payload: dict com metadados (inquerito_id, documento_id, pagina, etc.)
        """
        qdrant_points = [
            PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {}),
            )
            for p in points
        ]

        self.client.upsert(
            collection_name=self.collection_name,
            points=qdrant_points,
        )

    def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        inquerito_id: Optional[str] = None,
        tipo_documento: Optional[str] = None,
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
        )

        return [
            {
                "id": str(r.id),
                "score": r.score,
                "payload": r.payload,
            }
            for r in results
        ]

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
