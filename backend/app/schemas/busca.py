"""
Escrivão AI — Schemas: Busca RAG
Schemas para busca semântica nos chunks indexados.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class BuscaRequest(BaseModel):
    """Requisição de busca semântica."""
    query: str = Field(..., min_length=3, max_length=2000, description="Texto da consulta")
    inquerito_id: UUID = Field(..., description="ID do inquérito onde buscar")
    tipo_documento: Optional[str] = Field(None, description="Filtrar por tipo de peça")
    limit: int = Field(10, ge=1, le=50, description="Número máximo de resultados")
    score_minimo: Optional[float] = Field(None, ge=0.0, le=1.0, description="Score mínimo de similaridade")


class ChunkResultado(BaseModel):
    """Um chunk retornado pela busca."""
    chunk_id: str
    score: float
    texto_preview: str
    pagina_inicial: int
    pagina_final: int
    tipo_documento: str
    documento_id: str
    inquerito_id: str


class BuscaResponse(BaseModel):
    """Resposta da busca semântica."""
    query: str
    total_resultados: int
    resultados: List[ChunkResultado]


class StatusIndexacaoResponse(BaseModel):
    """Status da indexação de um inquérito no Qdrant."""
    inquerito_id: UUID
    total_chunks_indexados: int
    colecao_info: dict
