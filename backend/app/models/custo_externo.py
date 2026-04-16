"""
Escrivão AI — Modelo: CustoExterno
Registro manual de custos de serviços externos (Vercel, Supabase, Railway, Serper.dev).
Um registro por serviço por mês.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import String, DateTime, Text, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class CustoExterno(Base):
    __tablename__ = "custos_externos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    servico: Mapped[str] = mapped_column(String(40), nullable=False)   # "vercel", "supabase", "railway", "serper"
    mes: Mapped[str] = mapped_column(String(7), nullable=False)         # "2026-04"
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    custo_brl: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Origem do dado: manual | official_api | estimated | internal_telemetry
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    # Confiança da estimativa: high | medium | low
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="high")
    # Payload bruto retornado pela API do provedor (para auditoria)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("servico", "mes", name="uq_custos_externos_servico_mes"),
    )
