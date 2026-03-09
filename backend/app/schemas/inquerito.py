"""
Escrivão AI — Schemas: Inquérito
Schemas Pydantic para criação, resposta e transição de estado.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class InqueritoCreate(BaseModel):
    """Schema para criação de um novo inquérito."""
    numero: str = Field(..., min_length=1, max_length=100, description="Número do inquérito")
    delegacia: Optional[str] = Field(None, max_length=200, description="Delegacia responsável (legado)")
    ano: Optional[int] = Field(None, ge=1900, le=2100, description="Ano do inquérito")
    
    # Delegacia Atual / Redistribuição
    delegacia_atual_codigo: Optional[str] = Field(None, description="Código da delegacia atual (se redistribuído)")
    delegacia_atual_nome: Optional[str] = Field(None, description="Nome da delegacia atual")
    redistribuido: bool = Field(False, description="Indica se houve redistribuição")
    
    descricao: Optional[str] = Field(None, description="Descrição livre do caso")
    prioridade: Optional[str] = Field("media", description="alta, media ou baixa")
    classificacao_estrategica: Optional[str] = Field(
        None, description="Ex: alta_probabilidade, moderada, baixa_probabilidade, triagem, prescricao"
    )

class InqueritoUpdate(BaseModel):
    """Schema para atualização parcial."""
    descricao: Optional[str] = None
    prioridade: Optional[str] = None
    classificacao_estrategica: Optional[str] = None


class InqueritoResponse(BaseModel):
    """Schema de resposta de um inquérito."""
    id: UUID
    numero: str
    delegacia: Optional[str]
    
    delegacia_origem_codigo: Optional[str]
    delegacia_origem_nome: Optional[str]
    delegacia_atual_codigo: Optional[str]
    delegacia_atual_nome: Optional[str]
    redistribuido: bool
    
    ano: Optional[int]
    descricao: Optional[str]
    estado_atual: str
    prioridade: Optional[str]
    classificacao_estrategica: Optional[str]
    total_paginas: int
    total_documentos: int
    modo_grande: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InqueritoListResponse(BaseModel):
    """Lista paginada de inquéritos."""
    items: List[InqueritoResponse]
    total: int


class TransicaoEstadoRequest(BaseModel):
    """Schema para solicitar transição de estado."""
    novo_estado: str = Field(..., description="Estado destino")
    motivo: Optional[str] = Field(None, description="Motivo da transição")


class TransicaoEstadoResponse(BaseModel):
    """Resposta após transição de estado."""
    id: UUID
    estado_anterior: str
    estado_novo: str
    motivo: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class StatusInqueritoResponse(BaseModel):
    """Status completo do inquérito com ações e transições disponíveis."""
    id: UUID
    numero: str
    estado_atual: str
    descricao_estado: str
    acoes_disponiveis: List[str]
    transicoes_possiveis: List[str]
    total_paginas: int
    total_documentos: int
    modo_grande: bool


class MenuInicialResponse(BaseModel):
    """Menu de opções após carga do inquérito (§7.2 do blueprint)."""
    mensagem: str
    opcoes: List[dict]
