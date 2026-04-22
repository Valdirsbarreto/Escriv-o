"""
Escrivão AI — Modelo: OitivaGravada
Registro de oitivas transcritas e lavradas, associadas a pessoa e inquérito.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class OitivaGravada(Base):
    __tablename__ = "oitivas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    pessoa_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pessoas.id"), nullable=True, index=True
    )
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcricao_bruta: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Termo com [MM:SS] — exibido na tela com timestamps clicáveis
    termo_com_timestamps: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Termo limpo — para copiar e colar no sistema da PC (sem timestamps)
    termo_limpo: Mapped[str | None] = mapped_column(Text, nullable=True)
    duracao_segundos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "rascunho" | "finalizado"
    status: Mapped[str] = mapped_column(String(20), default="rascunho", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<OitivaGravada {self.id} [{self.status}]>"
