"""
Escrivão AI — Modelo: Intimação
Registra intimações extraídas de PDFs/fotos e vinculadas ao Google Agenda.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Intimacao(Base):
    __tablename__ = "intimacoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=True, index=True
    )
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documentos.id"), nullable=True, index=True
    )

    # ── Dados extraídos da intimação ─────────────────────
    intimado_nome: Mapped[str | None] = mapped_column(String(300), nullable=True)
    intimado_cpf: Mapped[str | None] = mapped_column(String(14), nullable=True)
    intimado_qualificacao: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # testemunha, investigado, vitima, perito, outro

    numero_inquerito_extraido: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # número conforme consta na intimação (antes do match com o BD)

    data_oitiva: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    local_oitiva: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # ── Google Calendar ────────────────────────────────────
    google_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    google_event_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Status ─────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(30), default="agendada", nullable=False
    )  # agendada, realizada, cancelada, erro_agenda

    # ── Arquivo original ───────────────────────────────────
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # ── Texto bruto extraído (para auditoria) ──────────────
    texto_extraido: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Intimacao {self.intimado_nome} — {self.data_oitiva}>"
