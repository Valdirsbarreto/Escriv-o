"""
Escrivão AI — Schemas: Intimação
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class IntimacaoResponse(BaseModel):
    id: UUID
    inquerito_id: Optional[UUID] = None
    documento_id: Optional[UUID] = None
    intimado_nome: Optional[str] = None
    intimado_cpf: Optional[str] = None
    intimado_qualificacao: Optional[str] = None
    numero_inquerito_extraido: Optional[str] = None
    data_oitiva: Optional[datetime] = None
    local_oitiva: Optional[str] = None
    google_event_id: Optional[str] = None
    google_event_url: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class IntimacaoUpdate(BaseModel):
    """Campos que o usuário pode corrigir manualmente."""
    intimado_nome: Optional[str] = None
    intimado_cpf: Optional[str] = None
    intimado_qualificacao: Optional[str] = None
    numero_inquerito_extraido: Optional[str] = None
    data_oitiva: Optional[datetime] = None
    local_oitiva: Optional[str] = None
    status: Optional[str] = None
    inquerito_id: Optional[UUID] = None


class IntimacaoUploadResponse(BaseModel):
    intimacao_id: UUID
    nome_arquivo: str
    status: str
    mensagem: str
    task_id: Optional[str] = None


class IntimacaoManualCreate(BaseModel):
    intimado_nome: str
    intimado_qualificacao: Optional[str] = None
    numero_inquerito_extraido: Optional[str] = None
    data_oitiva: datetime
    local_oitiva: Optional[str] = None
    inquerito_id: Optional[UUID] = None
