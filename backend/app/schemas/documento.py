"""
Escrivão AI — Schemas: Documento
Schemas para upload e resposta de documentos.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DocumentoResponse(BaseModel):
    """Schema de resposta de um documento."""
    id: UUID
    inquerito_id: UUID
    nome_arquivo: str
    tipo_documento: Optional[str]
    tipo_peca: Optional[str]
    hash_arquivo: Optional[str]
    total_paginas: int
    status_ocr: str
    status_processamento: str
    status_extracao_pecas: Optional[str] = None
    storage_path: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    """Resposta do upload de documento."""
    documento_id: UUID
    nome_arquivo: str
    status: str
    mensagem: str
    task_id: Optional[str] = None
