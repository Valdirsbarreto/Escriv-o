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

    VECTOR_SIZE = 768  # text-embedding-004

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
            logger.info(
                f"[QDRANT] Coleção principal '{self.collection_name}' criada (dims={size})"
            )
        else:
            logger.info(
                f"[QDRANT] Coleção principal '{self.collection_name}' já existe"
            )

        if "casos_historicos" not in names:
            self.client.create_collection(
                collection_name="casos_historicos",
                vectors_config=VectorParams(
                    size=size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                f"[QDRANT] Coleção de jurisprudência 'casos_historicos' criada (dims={size})"
            )
        else:
            logger.info("[QDRANT] Coleção 'casos_historicos' já existe")

    def recreate_collection(self, vector_size: int = None) -> Dict[str, Any]:
        """
        Apaga e recria a coleção com as dimensões corretas.
        ATENÇÃO: todos os vetores indexados serão perdidos — re-indexar os documentos após.
        """
        size = vector_size or self.VECTOR_SIZE
        try:
            self.client.delete_collection(self.collection_name)
            logger.warning(f"[QDRANT] Coleção '{self.collection_name}' apagada")
        except Exception:
            pass  # Pode não existir

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )
        logger.info(f"[QDRANT] Coleção '{self.collection_name}' recriada (dims={size})")
        return {"ok": True, "collection": self.collection_name, "dims": size}

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
        collection_name: Optional[str] = None,
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
        target_collection = collection_name or self.collection_name

        results = self.client.search(
            collection_name=target_collection,
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

    def delete_by_documento(self, documento_id: str) -> None:
        """Remove todos os pontos de um documento específico."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="documento_id",
                            match=MatchValue(value=documento_id),
                        )
                    ]
                ),
            )
            logger.info(f"[QDRANT] Pontos removidos para documento {documento_id}")
        except Exception as e:
            logger.warning(f"[QDRANT] Falha ao remover pontos do documento {documento_id}: {e}")

    def set_payload_by_documento(self, documento_id: str, payload_update: Dict[str, Any]) -> None:
        """Atualiza campos do payload em todos os chunks de um documento."""
        try:
            self.client.set_payload(
                collection_name=self.collection_name,
                payload=payload_update,
                points=Filter(
                    must=[
                        FieldCondition(
                            key="documento_id",
                            match=MatchValue(value=documento_id),
                        )
                    ]
                ),
            )
            logger.info(f"[QDRANT] Payload atualizado para documento {documento_id}: {list(payload_update.keys())}")
        except Exception as e:
            logger.warning(f"[QDRANT] Falha ao atualizar payload do documento {documento_id}: {e}")

    def scroll_by_documento(self, documento_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Retorna todos os chunks de um documento, ordenados por página."""
        try:
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="documento_id",
                            match=MatchValue(value=documento_id),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            chunks = [
                {
                    "chunk_id": str(r.id),
                    "pagina_inicial": r.payload.get("pagina_inicial"),
                    "pagina_final": r.payload.get("pagina_final"),
                    "tipo_peca": r.payload.get("tipo_peca", ""),
                    "texto": r.payload.get("texto_preview", ""),
                }
                for r in results
            ]
            # Ordenar por página
            chunks.sort(key=lambda x: x["pagina_inicial"] or 0)
            return chunks
        except Exception as e:
            logger.warning(f"[QDRANT] Falha ao buscar chunks do documento {documento_id}: {e}")
            return []

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
