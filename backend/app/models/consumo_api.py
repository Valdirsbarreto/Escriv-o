"""
Escrivão AI — Modelo: ConsumoApi
Registro de cada chamada LLM: tokens, custo em BRL, agente responsável.
Permite dashboard de orçamento e alertas de limite.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, DateTime, Integer, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ConsumoApi(Base):
    __tablename__ = "consumo_api"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    # Identificação do chamador
    agente: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True
    )  # Ex: 'Copiloto', 'AgenteFicha', 'Resumo', 'NER', 'Orquestrador'

    modelo: Mapped[str] = mapped_column(
        String(60), nullable=False
    )  # Ex: 'gemini-1.5-pro', 'gemini-1.5-flash-8b'

    tier: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'economico' | 'standard' | 'premium'

    tokens_prompt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_saida: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Custo em USD (base de cálculo)
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)

    # Custo convertido para BRL (custo_usd × cotacao_dolar)
    custo_brl: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)

    # Cotação usada na conversão (referência histórica)
    cotacao_dolar: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=5.80)

    # Índice por mês para queries de saldo mensal
    __table_args__ = (
        Index("ix_consumo_api_agente_timestamp", "agente", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<ConsumoApi agente={self.agente} modelo={self.modelo} "
            f"tokens={self.tokens_prompt}+{self.tokens_saida} brl=R${self.custo_brl}>"
        )
