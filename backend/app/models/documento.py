"""
Escrivão AI — Modelo: Documento
Representa um arquivo PDF/imagem importado em um inquérito.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    nome_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_documento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hash_arquivo: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_paginas: Mapped[int] = mapped_column(Integer, default=0)
    texto_extraido: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_ocr: Mapped[str] = mapped_column(
        String(30), default="pendente", nullable=False
    )
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status_processamento: Mapped[str] = mapped_column(
        String(30), default="pendente", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    inquerito = relationship("Inquerito", back_populates="documentos")
    chunks = relationship("Chunk", back_populates="documento", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Documento {self.nome_arquivo}>"
