"""Escrivão AI — Modelo: Peça Extraída (sub-documento identificado dentro de um PDF)"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class PecaExtraida(Base):
    __tablename__ = "pecas_extraidas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    documento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documentos.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    # Título descritivo gerado pela IA: ex. "Termo de Declaração de Flávio Luiz Lemos"
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    # Tipo da peça: termo_declaracao | auto_apreensao | oficio | laudo | bo | despacho | portaria | outro
    tipo: Mapped[str] = mapped_column(String(80), nullable=False, default="outro")
    # Texto completo da peça (ipsis litteris, como extraído do PDF)
    conteudo_texto: Mapped[str] = mapped_column(Text, nullable=False)
    # Localização aproximada dentro do PDF (opcional)
    pagina_inicial: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pagina_final: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Resumo de 2-3 linhas gerado pela IA
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
