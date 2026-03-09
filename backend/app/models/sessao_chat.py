"""
Escrivão AI — Modelo: Sessão de Chat
Gerencia sessões de conversa com o copiloto investigativo.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class SessaoChat(Base):
    __tablename__ = "sessoes_chat"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    titulo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contexto: Mapped[str | None] = mapped_column(
        String(50), default="copiloto"
    )  # copiloto, triagem, oitiva, etc.
    total_mensagens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ativa: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relacionamentos
    mensagens = relationship("MensagemChat", back_populates="sessao", order_by="MensagemChat.created_at")

    def __repr__(self) -> str:
        return f"<SessaoChat {self.id} - {self.contexto}>"
