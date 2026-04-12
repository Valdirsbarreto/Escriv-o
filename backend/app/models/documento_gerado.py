"""Escrivão AI — Modelo: Documento Gerado pela IA"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, func, Float, Integer
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
    
    # Metadados de IA / Auditoria
    modelo_llm: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tokens_prompt: Mapped[Optional[int]] = mapped_column(nullable=True)
    tokens_resposta: Mapped[Optional[int]] = mapped_column(nullable=True)
    custo_estimado: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
