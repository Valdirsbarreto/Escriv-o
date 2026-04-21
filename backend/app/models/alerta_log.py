"""
Escrivão AI — Modelo: AlertaLog
Persiste alertas do sistema para o painel in-app de notificações.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class AlertaLog(Base):
    __tablename__ = "alertas_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nivel: Mapped[str] = mapped_column(String(10), nullable=False)  # critico | alerta | info
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)       # texto limpo para "Copiar para Claude"
    mensagem_html: Mapped[str] = mapped_column(Text, nullable=False)  # HTML para Telegram
    identificador: Mapped[str | None] = mapped_column(String(200), nullable=True)  # doc_id | task_id | inq_id
    lido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<AlertaLog {self.tipo} [{self.nivel}] lido={self.lido}>"
