"""
Escrivão AI — Modelo: ConsultaExterna
Auditoria de consultas pagas às APIs externas (direct.data).
Serve para rastrear custos por inquérito, evitar cobranças duplicadas (cache)
e cumprir requisitos de auditoria/LGPD.
"""

import hashlib
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import String, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class ConsultaExterna(Base):
    __tablename__ = "consultas_externas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inquerito_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inqueritos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Ex: "cadastro_pf_plus", "mandados_prisao", "ceis", "consulta_veicular"
    tipo_consulta: Mapped[str] = mapped_column(String(60), nullable=False)

    # SHA-256[:16] do documento limpo — identifica o alvo sem expor o dado
    documento_hash: Mapped[str] = mapped_column(String(16), nullable=False)

    # Custo em reais da consulta (estimado com base no cardápio)
    custo_estimado: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    # "ok" | "nao_encontrado" | "erro" | "timeout"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")

    # JSON retornado pela API (None em caso de erro)
    resultado_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    # Índice composto para lookup de cache: mesma consulta, mesmo doc, mesmo inquérito
    __table_args__ = (
        Index(
            "ix_consultas_externas_cache",
            "inquerito_id",
            "tipo_consulta",
            "documento_hash",
        ),
    )

    def __repr__(self) -> str:
        return f"<ConsultaExterna tipo={self.tipo_consulta} hash={self.documento_hash} status={self.status}>"

    @staticmethod
    def hash_documento(documento_limpo: str) -> str:
        """Gera hash SHA-256[:16] de um documento (CPF/CNPJ/Placa limpo)."""
        return hashlib.sha256(documento_limpo.encode()).hexdigest()[:16]
