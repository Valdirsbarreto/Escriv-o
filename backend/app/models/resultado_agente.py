"""
Escrivão AI — Modelo: ResultadoAgente
Persiste outputs gerados pelos agentes especializados.
Conforme blueprint §9 (Agentes Especializados).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class ResultadoAgente(Base):
    __tablename__ = "resultados_agentes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    # ficha_pessoa | ficha_empresa | cautelar | extrato
    tipo_agente: Mapped[str] = mapped_column(String(30), nullable=False)
    # UUID da entidade alvo (pessoa_id, empresa_id, documento_id, etc.)
    referencia_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    resultado_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    texto_gerado: Mapped[str | None] = mapped_column(Text, nullable=True)
    modelo_llm: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<ResultadoAgente tipo={self.tipo_agente} ref={self.referencia_id}>"
