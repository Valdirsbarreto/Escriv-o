"""
Escrivão AI — Modelo: Inquérito
Tabela principal que representa um inquérito policial.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.state_machine import EstadoInquerito


class Inquerito(Base):
    __tablename__ = "inqueritos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    numero: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    delegacia: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ano: Mapped[int | None] = mapped_column(nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)

    estado_atual: Mapped[str] = mapped_column(
        String(50),
        default=EstadoInquerito.RECEBIDO.value,
        nullable=False,
        index=True,
    )

    prioridade: Mapped[str | None] = mapped_column(
        String(20), default="media", nullable=True
    )
    classificacao_estrategica: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    total_paginas: Mapped[int] = mapped_column(default=0)
    total_documentos: Mapped[int] = mapped_column(default=0)
    modo_grande: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    documentos = relationship("Documento", back_populates="inquerito", lazy="selectin")
    transicoes = relationship("TransicaoEstado", back_populates="inquerito", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Inquerito {self.numero} [{self.estado_atual}]>"
