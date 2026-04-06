"""Escrivão AI — Modelo: Documento Gerado pela IA"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class DocumentoGerado(Base):
    __tablename__ = "documentos_gerados"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inquerito_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inqueritos.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, default="outro")
    # tipos: roteiro_oitiva | oficio | minuta_cautelar | relatorio | outro
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
