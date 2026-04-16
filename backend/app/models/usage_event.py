"""
Escrivão AI — Modelo: UsageEvent
Telemetria interna de uso de APIs externas cobradas por requisição
(Serper.dev, direct.data, etc.). Usado para estimativa de custo quando
o provedor não expõe billing por API.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import String, DateTime, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)   # "serper", "directdata"
    metric: Mapped[str] = mapped_column(String(60), nullable=False)     # "search_query", "person_lookup"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cost_estimate_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)     # dados extras (query, nome, etc.)
