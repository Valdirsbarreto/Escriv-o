"""
Escrivão AI — Schemas: Índices e Entidades
Schemas Pydantic para retorno de dados extraídos por NER.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PessoaOut(BaseModel):
    id: UUID
    nome: str
    cpf: Optional[str] = None
    tipo_pessoa: Optional[str] = None
    observacoes: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EmpresaOut(BaseModel):
    id: UUID
    nome: str
    cnpj: Optional[str] = None
    tipo_empresa: Optional[str] = None
    observacoes: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EnderecoOut(BaseModel):
    id: UUID
    endereco_completo: str
    cidade: Optional[str] = None
    estado: Optional[str] = None
    cep: Optional[str] = None
    pessoa_id: Optional[UUID] = None
    empresa_id: Optional[UUID] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ContatoOut(BaseModel):
    id: UUID
    tipo_contato: str
    valor: str
    pessoa_id: Optional[UUID] = None
    empresa_id: Optional[UUID] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EventoCronologicoOut(BaseModel):
    id: UUID
    data_fato: Optional[datetime] = None
    data_fato_str: Optional[str] = None
    descricao: str
    documento_id: Optional[UUID] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
