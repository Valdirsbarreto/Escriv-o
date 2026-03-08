"""
Escrivão AI — Modelo: Tarefa de Agente
Registra cada tarefa executada por um agente, com custo e modelo utilizado.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class TarefaAgente(Base):
    __tablename__ = "tarefas_agentes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    agente: Mapped[str] = mapped_column(String(100), nullable=False)
    comando_usuario: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="pendente", nullable=False
    )
    modelo_utilizado: Mapped[str | None] = mapped_column(String(100), nullable=True)
    custo_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    tempo_execucao_ms: Mapped[int | None] = mapped_column(nullable=True)
    resultado_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<TarefaAgente {self.agente} [{self.status}]>"
