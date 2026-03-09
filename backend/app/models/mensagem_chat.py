"""
Escrivão AI — Modelo: Mensagem de Chat
Armazena cada mensagem trocada em uma sessão de conversa.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class MensagemChat(Base):
    __tablename__ = "mensagens_chat"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sessao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessoes_chat.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # user, assistant, system
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    fontes: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # Lista de chunks/páginas citados
    modelo_utilizado: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_prompt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_resposta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custo_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    tempo_resposta_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relacionamentos
    sessao = relationship("SessaoChat", back_populates="mensagens")

    def __repr__(self) -> str:
        return f"<MensagemChat {self.role}: {self.conteudo[:50]}...>"
