"""
Escrivão AI — Modelo: ResumoCache
Cache de resumos hierárquicos gerados por LLM.
Conforme blueprint §6.4 (Resumos Hierárquicos).
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ResumoCache(Base):
    __tablename__ = "resumos_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    # Nível hierárquico: pagina | documento | volume | caso
    nivel: Mapped[str] = mapped_column(String(20), nullable=False)
    # UUID da entidade correspondente (documento_id, volume_id, etc). None = nível "caso"
    referencia_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    texto_resumo: Mapped[str] = mapped_column(Text, nullable=False)
    modelo_llm: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_usados: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<ResumoCache nivel={self.nivel} ref={self.referencia_id}>"
