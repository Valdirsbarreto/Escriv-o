"""
Escrivão AI — Modelo: Auditoria
Registro de auditoria factual/jurídica de resultados de agentes.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class Auditoria(Base):
    __tablename__ = "auditorias"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tarefa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tarefas_agentes.id"), nullable=False, index=True
    )
    tipo_auditoria: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # factual, fonte_pagina, prudencia, juridica
    status: Mapped[str] = mapped_column(
        String(30), default="pendente", nullable=False
    )  # pendente, aprovado, reprovado, revisao_necessaria
    inconsistencias_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    aprovado_por_usuario: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Auditoria {self.tipo_auditoria} [{self.status}]>"
