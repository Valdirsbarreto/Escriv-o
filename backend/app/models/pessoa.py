"""
Escrivão AI — Modelo: Pessoa
Pessoas identificadas nos autos de um inquérito.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Pessoa(Base):
    __tablename__ = "pessoas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo_pessoa: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # testemunha, vitima, investigado, outro
    cpf: Mapped[str | None] = mapped_column(String(14), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Pessoa {self.nome} ({self.tipo_pessoa})>"
