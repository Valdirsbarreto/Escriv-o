"""
Escrivão AI — PgvectorService
Substituição do QdrantService: busca vetorial via PostgreSQL + extensão pgvector.
Interface compatível com QdrantService para migração drop-in.
"""

import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class PgvectorService:
    """
    Busca vetorial usando pgvector no PostgreSQL.
    Substitui QdrantService — mesma interface de retorno.

    Uso (endpoints async):
        pgvector = PgvectorService(db)  # db = AsyncSession
        resultados = await pgvector.search(query_vector, inquerito_id=...)
    """

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _vec(vector: List[float]) -> str:
        return "[" + ",".join(str(v) for v in vector) + "]"

    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        inquerito_id: Optional[str] = None,
        tipo_documento: Optional[str] = None,
        score_threshold: Optional[float] = None,
        collection_name: Optional[str] = None,  # ignorado — compat com QdrantService
    ) -> List[Dict[str, Any]]:
        """Busca vetorial por similaridade coseno com filtros opcionais."""
        from sqlalchemy import text

        vec = self._vec(query_vector)
        where: List[str] = ["c.embedding IS NOT NULL"]
        params: Dict[str, Any] = {"vec": vec, "limit": limit}

        if inquerito_id:
            where.append("c.inquerito_id = CAST(:inq_id AS uuid)")
            params["inq_id"] = inquerito_id
        if tipo_documento:
            where.append("c.tipo_documento = :tipo_doc")
            params["tipo_doc"] = tipo_documento
        if score_threshold is not None:
            where.append("1 - (c.embedding <=> CAST(:vec AS vector)) >= :threshold")
            params["threshold"] = score_threshold

        sql = text(f"""
            SELECT
                c.id::text           AS id,
                c.documento_id::text AS documento_id,
                c.inquerito_id::text AS inquerito_id,
                c.pagina_inicial,
                c.pagina_final,
                c.tipo_documento,
                d.tipo_peca,
                c.texto,
                1 - (c.embedding <=> CAST(:vec AS vector)) AS score
            FROM chunks c
            LEFT JOIN documentos d ON d.id = c.documento_id
            WHERE {" AND ".join(where)}
            ORDER BY c.embedding <=> CAST(:vec AS vector)
            LIMIT :limit
        """)

        result = await self.db.execute(sql, params)
        rows = result.mappings().all()

        return [
            {
                "id": row["id"],
                "score": float(row["score"] or 0.0),
                "payload": {
                    "inquerito_id": row["inquerito_id"],
                    "documento_id": row["documento_id"],
                    "chunk_id": row["id"],
                    "pagina_inicial": row["pagina_inicial"],
                    "pagina_final": row["pagina_final"],
                    "tipo_documento": row["tipo_documento"] or "",
                    "tipo_peca": row["tipo_peca"] or "",
                    "texto_preview": (row["texto"] or "")[:500],
                },
            }
            for row in rows
        ]

    async def count_by_inquerito(self, inquerito_id: str) -> int:
        from sqlalchemy import text
        result = await self.db.execute(
            text(
                "SELECT COUNT(*) FROM chunks "
                "WHERE inquerito_id = CAST(:id AS uuid) AND embedding IS NOT NULL"
            ),
            {"id": inquerito_id},
        )
        return result.scalar() or 0

    async def get_collection_info(self) -> Dict[str, Any]:
        from sqlalchemy import text
        try:
            result = await self.db.execute(
                text("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
            )
            total = result.scalar() or 0
            return {
                "nome": "chunks (pgvector)",
                "total_pontos": total,
                "vetores_indexados": total,
                "status": "green",
            }
        except Exception as e:
            return {"erro": str(e)}

    async def scroll_by_documento(
        self, documento_id: str, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Retorna todos os chunks de um documento ordenados por página."""
        from sqlalchemy import text
        try:
            result = await self.db.execute(
                text("""
                    SELECT
                        id::text          AS chunk_id,
                        pagina_inicial,
                        pagina_final,
                        tipo_documento    AS tipo_peca,
                        LEFT(texto, 500)  AS texto
                    FROM chunks
                    WHERE documento_id = CAST(:doc_id AS uuid)
                    ORDER BY pagina_inicial
                    LIMIT :limit
                """),
                {"doc_id": documento_id, "limit": limit},
            )
            return [dict(r) for r in result.mappings().all()]
        except Exception as e:
            logger.warning(f"[PGVECTOR] scroll_by_documento falhou ({documento_id}): {e}")
            return []
