"""
Escrivão AI — Schemas: Chat e Copiloto
Schemas para sessões de chat e interação com o copiloto.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Sessão ────────────────────────────────────────────────

class SessaoChatCreate(BaseModel):
    """Criar nova sessão de chat."""
    inquerito_id: UUID
    contexto: str = Field("copiloto", description="copiloto, triagem, oitiva, etc.")
    titulo: Optional[str] = None


class SessaoChatResponse(BaseModel):
    """Resposta de sessão de chat."""
    id: UUID
    inquerito_id: UUID
    titulo: Optional[str]
    contexto: str
    total_mensagens: int
    total_tokens: int
    ativa: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Mensagem ──────────────────────────────────────────────

class MensagemRequest(BaseModel):
    """Enviar mensagem ao copiloto."""
    mensagem: str = Field(..., min_length=2, max_length=5000, description="Pergunta ou instrução")
    auditar: bool = Field(True, description="Se True, audita factualmente a resposta")


class FonteCitada(BaseModel):
    """Uma fonte citada na resposta."""
    documento_id: str
    pagina_inicial: int
    pagina_final: int
    score: float
    tipo_documento: str


class AuditoriaResponse(BaseModel):
    """Resultado da auditoria factual."""
    status: Optional[str] = None
    score_confiabilidade: Optional[float] = None
    citacoes_ausentes: Optional[List[str]] = None
    distorcoes: Optional[List[str]] = None
    extrapolacoes: Optional[List[str]] = None
    recomendacao: Optional[str] = None
    modelo_auditor: Optional[str] = None
    custo_auditoria: Optional[float] = None


class MensagemResponse(BaseModel):
    """Resposta do copiloto com fontes e auditoria."""
    resposta: str
    fontes: List[FonteCitada]
    auditoria: Optional[Dict[str, Any]] = None
    modelo: str
    tokens_prompt: int
    tokens_resposta: int
    custo_estimado: float
    tempo_total_ms: int


class MensagemChatResponse(BaseModel):
    """Mensagem armazenada do chat."""
    id: UUID
    role: str
    conteudo: str
    fontes: Optional[Dict[str, Any]] = None
    modelo_utilizado: Optional[str] = None
    tokens_prompt: Optional[int] = None
    tokens_resposta: Optional[int] = None
    custo_estimado: Optional[float] = None
    tempo_resposta_ms: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoricoResponse(BaseModel):
    """Histórico completo de uma sessão."""
    sessao: SessaoChatResponse
    mensagens: List[MensagemChatResponse]
