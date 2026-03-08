"""
Escrivão AI — Modelo: Chunk
Bloco semântico extraído de um documento para indexação vetorial.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    documento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documentos.id"), nullable=False, index=True
    )

    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pagina_inicial: Mapped[int] = mapped_column(Integer, nullable=False)
    pagina_final: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo_documento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    titulo_detectado: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pessoa_principal: Mapped[str | None] = mapped_column(String(300), nullable=True)

    texto: Mapped[str] = mapped_column(Text, nullable=False)
    resumo_curto: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    documento = relationship("Documento", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<Chunk p.{self.pagina_inicial}-{self.pagina_final}>"
