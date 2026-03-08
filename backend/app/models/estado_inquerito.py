"""
Escrivão AI — Modelo: Transição de Estado
Histórico de todas as transições de estado de um inquérito.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class TransicaoEstado(Base):
    __tablename__ = "transicoes_estado"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    estado_anterior: Mapped[str] = mapped_column(String(50), nullable=False)
    estado_novo: Mapped[str] = mapped_column(String(50), nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    inquerito = relationship("Inquerito", back_populates="transicoes")

    def __repr__(self) -> str:
        return f"<Transicao {self.estado_anterior} -> {self.estado_novo}>"
