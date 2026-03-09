"""
Escrivão AI — Modelo: Evento Cronologico
Eventos temporais para formar a linha do tempo narrativa do inquérito.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class EventoCronologico(Base):
    __tablename__ = "eventos_cronologicos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    data_fato: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_fato_str: Mapped[str | None] = mapped_column(String(50), nullable=True) # Para datas imprecisas como "Meados de 2023"
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documentos.id", ondelete="SET NULL"), nullable=True
    )
    pagina_referencia: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<EventoCronologico {self.data_fato_str or self.data_fato}>"
