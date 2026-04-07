"""
Escrivão AI — Banco de Casos Gold (Pilar B — Faro Investigativo)
Gerencia a coleção Qdrant 'casos_historicos' com sentenças e laudos de sucesso.
Utilizada como few-shot contextual nas sínteses investigativas.
"""

import logging
import uuid
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

TIPOS_CASO_VALIDOS = {
    "sentenca_condenatoria",
    "sentenca_absolutoria",
    "acordao_tjsp",
    "laudo_pericial_referencia",
    "relatorio_policial_modelo",
    "outro",
}

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


def _chunk_text(texto: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Divide texto em chunks com overlap por caracteres."""
    if not texto:
        return []
    chunks = []
    start = 0
    while start < len(texto):
        end = start + chunk_size
        chunk = texto[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end >= len(texto):
            break
        start = end - overlap
    return chunks


class CasosGoldService:
    """Gerencia a coleção Qdrant 'casos_historicos' — Banco de Casos Gold."""

    def __init__(self):
        # Imports pesados são lazy (dentro dos métodos)
        from app.services.embedding_service import EmbeddingService
        self.embedding_service = EmbeddingService()
        self.collection_name = settings.QDRANT_COLLECTION_CASOS

    def _get_qdrant(self):
        """Retorna cliente Qdrant (lazy import)."""
        from qdrant_client import QdrantClient
        return QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )

    async def garantir_colecao(self) -> None:
        """Cria a coleção 'casos_historicos' no Qdrant se não existir (768 dims, cosine)."""
        from qdrant_client.models import Distance, VectorParams

        client = self._get_qdrant()
        try:
            collections = client.get_collections().collections
            names = [c.name for c in collections]
            if self.collection_name not in names:
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=768,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(
                    f"[CASOS-GOLD] Coleção '{self.collection_name}' criada (dims=768, cosine)"
                )
            else:
                logger.info(f"[CASOS-GOLD] Coleção '{self.collection_name}' já existe")
        except Exception as e:
            logger.error(f"[CASOS-GOLD] Erro ao garantir coleção: {e}")
            raise

    async def ingerir_caso(
        self,
        titulo: str,
        tipo: str,
        conteudo_texto: str,
        metadata: dict,
    ) -> str:
        """
        Chunka o texto, gera embeddings e upserta na coleção 'casos_historicos'.
        Retorna o caso_id (UUID gerado).
        """
        from qdrant_client.models import PointStruct

        if tipo not in TIPOS_CASO_VALIDOS:
            logger.warning(
                f"[CASOS-GOLD] Tipo '{tipo}' não reconhecido — usando 'outro'"
            )
            tipo = "outro"

        caso_id = str(uuid.uuid4())

        await self.garantir_colecao()

        chunks = _chunk_text(conteudo_texto, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        if not chunks:
            logger.warning(f"[CASOS-GOLD] Nenhum chunk gerado para caso '{titulo}'")
            return caso_id

        logger.info(
            f"[CASOS-GOLD] Gerando embeddings para {len(chunks)} chunks do caso '{titulo}'"
        )

        points = []
        for idx, chunk_text in enumerate(chunks):
            vector = await self.embedding_service.agenerate(chunk_text)

            payload = {
                "caso_id": caso_id,
                "titulo": titulo,
                "tipo": tipo,
                "chunk_index": idx,
                "texto": chunk_text,
                **metadata,
            }

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload,
                )
            )

        client = self._get_qdrant()
        batch_size = 50
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )
            logger.info(
                f"[CASOS-GOLD] Batch {i // batch_size + 1}: {len(batch)} pontos inseridos"
            )

        logger.info(
            f"[CASOS-GOLD] Caso '{titulo}' ({tipo}) indexado — caso_id={caso_id}, "
            f"{len(points)} chunks"
        )
        return caso_id

    async def buscar_casos_similares(
        self,
        query: str,
        tipo_crime: Optional[str] = None,
        top_k: int = 3,
    ) -> list[dict]:
        """
        Busca semântica na coleção 'casos_historicos'.
        Retorna lista de {titulo, tipo, texto, score, metadata}.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        vector = await self.embedding_service.agenerate(query)
        if not any(v != 0.0 for v in vector[:10]):
            logger.warning("[CASOS-GOLD] Embedding nulo — busca de casos cancelada")
            return []

        filters = []
        if tipo_crime:
            filters.append(
                FieldCondition(
                    key="tipo",
                    match=MatchValue(value=tipo_crime),
                )
            )

        search_filter = Filter(must=filters) if filters else None

        client = self._get_qdrant()
        try:
            results = client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=top_k,
                query_filter=search_filter,
                with_payload=True,
                score_threshold=0.5,
            )
        except Exception as e:
            logger.error(f"[CASOS-GOLD] Erro na busca vetorial: {e}")
            return []

        casos = []
        for r in results:
            payload = r.payload or {}
            # Monta metadata excluindo campos estruturais
            meta_keys = {"caso_id", "titulo", "tipo", "chunk_index", "texto"}
            meta = {k: v for k, v in payload.items() if k not in meta_keys}
            casos.append(
                {
                    "titulo": payload.get("titulo", ""),
                    "tipo": payload.get("tipo", ""),
                    "texto": payload.get("texto", ""),
                    "score": round(r.score, 4),
                    "metadata": meta,
                }
            )

        logger.info(
            f"[CASOS-GOLD] Busca '{query[:60]}' → {len(casos)} caso(s) encontrado(s)"
        )
        return casos

    def listar_casos(self, limit: int = 50) -> list[dict]:
        """
        Lista os casos indexados via scroll — retorna um item por caso_id único.
        """
        client = self._get_qdrant()
        try:
            results, _ = client.scroll(
                collection_name=self.collection_name,
                limit=limit * 5,  # busca mais para deduplicar por caso_id
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            logger.error(f"[CASOS-GOLD] Erro ao listar casos: {e}")
            return []

        vistos: set[str] = set()
        casos = []
        for r in results:
            payload = r.payload or {}
            caso_id = payload.get("caso_id", "")
            if caso_id and caso_id not in vistos:
                vistos.add(caso_id)
                meta_keys = {"caso_id", "titulo", "tipo", "chunk_index", "texto"}
                meta = {k: v for k, v in payload.items() if k not in meta_keys}
                casos.append(
                    {
                        "caso_id": caso_id,
                        "titulo": payload.get("titulo", ""),
                        "tipo": payload.get("tipo", ""),
                        "metadata": meta,
                    }
                )
            if len(casos) >= limit:
                break

        return casos

    def deletar_caso(self, caso_id: str) -> int:
        """Remove todos os pontos com caso_id == {caso_id} do Qdrant. Retorna total removido."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = self._get_qdrant()
        try:
            # Conta antes de deletar
            result = client.count(
                collection_name=self.collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="caso_id",
                            match=MatchValue(value=caso_id),
                        )
                    ]
                ),
            )
            total = result.count

            client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="caso_id",
                            match=MatchValue(value=caso_id),
                        )
                    ]
                ),
            )
            logger.info(
                f"[CASOS-GOLD] {total} ponto(s) removido(s) para caso_id={caso_id}"
            )
            return total
        except Exception as e:
            logger.error(f"[CASOS-GOLD] Erro ao deletar caso {caso_id}: {e}")
            raise
