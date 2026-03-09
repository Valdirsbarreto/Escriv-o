"""
Escrivão AI — Modelo: Contato
Telefones, e-mails e redes sociais identificados.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Contato(Base):
    __tablename__ = "contatos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inqueritos.id"), nullable=False, index=True
    )
    tipo_contato: Mapped[str] = mapped_column(String(50), nullable=False)  # telefone, email, rede_social
    valor: Mapped[str] = mapped_column(String(255), nullable=False)
    
    pessoa_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pessoas.id", ondelete="SET NULL"), nullable=True
    )
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="SET NULL"), nullable=True
    )

    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Contato {self.tipo_contato}: {self.valor}>"
