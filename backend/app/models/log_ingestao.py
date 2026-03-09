"""
Escrivão AI — Modelo: Log de Ingestão
Rastreio granular de cada etapa do pipeline de ingestão.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class LogIngestao(Base):
    __tablename__ = "logs_ingestao"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    documento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documentos.id"), nullable=False, index=True
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    etapa: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # upload, extracao, ocr, chunking, embedding, indexacao
    status: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # iniciado, concluido, erro, pulado
    detalhes: Mapped[str | None] = mapped_column(Text, nullable=True)
    dados_extras: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duracao_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<LogIngestao {self.etapa} [{self.status}]>"
