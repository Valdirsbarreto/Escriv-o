"""
Escrivão AI — API de Controle de Orçamento LLM
Endpoints para dashboard financeiro: saldo, ranking por agente, histórico diário.
"""

from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.config import settings
from app.models.consumo_api import ConsumoApi

router = APIRouter(prefix="/consumo", tags=["Orçamento"])


def _inicio_mes_atual() -> datetime:
    now = datetime.utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/saldo")
async def saldo_orcamento(db: AsyncSession = Depends(get_db)):
    """
    Retorna o saldo disponível do mês corrente.
    Fórmula: R$ 250,00 - soma de custo_brl do mês.
    """
    inicio = _inicio_mes_atual()

    result = await db.execute(
        select(
            func.coalesce(func.sum(ConsumoApi.custo_brl), 0).label("gasto_total"),
            func.coalesce(func.sum(ConsumoApi.tokens_prompt + ConsumoApi.tokens_saida), 0).label("tokens_total"),
            func.count(ConsumoApi.id).label("chamadas"),
        ).where(ConsumoApi.timestamp >= inicio)
    )
    row = result.one()

    gasto = float(row.gasto_total)
    budget = settings.BUDGET_BRL
    saldo = budget - gasto
    pct_usado = (gasto / budget * 100) if budget > 0 else 0

    return {
        "mes_referencia": inicio.strftime("%Y-%m"),
        "budget_brl": budget,
        "gasto_brl": round(gasto, 4),
        "saldo_brl": round(saldo, 4),
        "percentual_usado": round(pct_usado, 1),
        "tokens_total": int(row.tokens_total),
        "chamadas_total": int(row.chamadas),
        "alerta_ativo": gasto >= settings.BUDGET_ALERT_BRL,
        "cotacao_dolar": settings.COTACAO_DOLAR,
    }


@router.get("/ranking")
async def ranking_por_agente(db: AsyncSession = Depends(get_db)):
    """
    Ranking de gastos por agente no mês corrente.
    Útil para identificar qual componente está consumindo mais orçamento.
    """
    inicio = _inicio_mes_atual()

    result = await db.execute(
        select(
            ConsumoApi.agente,
            ConsumoApi.tier,
            func.sum(ConsumoApi.custo_brl).label("gasto_brl"),
            func.sum(ConsumoApi.custo_usd).label("gasto_usd"),
            func.sum(ConsumoApi.tokens_prompt).label("tokens_prompt"),
            func.sum(ConsumoApi.tokens_saida).label("tokens_saida"),
            func.count(ConsumoApi.id).label("chamadas"),
        )
        .where(ConsumoApi.timestamp >= inicio)
        .group_by(ConsumoApi.agente, ConsumoApi.tier)
        .order_by(func.sum(ConsumoApi.custo_brl).desc())
    )
    rows = result.all()

    return [
        {
            "agente": r.agente,
            "tier": r.tier,
            "gasto_brl": round(float(r.gasto_brl), 4),
            "gasto_usd": round(float(r.gasto_usd), 6),
            "tokens_prompt": int(r.tokens_prompt),
            "tokens_saida": int(r.tokens_saida),
            "chamadas": int(r.chamadas),
        }
        for r in rows
    ]


@router.get("/historico")
async def historico_diario(dias: int = 30, db: AsyncSession = Depends(get_db)):
    """
    Gasto diário dos últimos N dias (padrão: 30).
    Ideal para gráfico de linha no frontend.
    """
    inicio = datetime.utcnow() - timedelta(days=dias)

    result = await db.execute(
        select(
            func.date_trunc("day", ConsumoApi.timestamp).label("dia"),
            func.sum(ConsumoApi.custo_brl).label("gasto_brl"),
            func.count(ConsumoApi.id).label("chamadas"),
        )
        .where(ConsumoApi.timestamp >= inicio)
        .group_by(func.date_trunc("day", ConsumoApi.timestamp))
        .order_by(func.date_trunc("day", ConsumoApi.timestamp))
    )
    rows = result.all()

    return [
        {
            "dia": r.dia.strftime("%Y-%m-%d"),
            "gasto_brl": round(float(r.gasto_brl), 4),
            "chamadas": int(r.chamadas),
        }
        for r in rows
    ]


@router.get("/modelos")
async def ranking_por_modelo(db: AsyncSession = Depends(get_db)):
    """Breakdown de custo por modelo LLM no mês corrente."""
    inicio = _inicio_mes_atual()

    result = await db.execute(
        select(
            ConsumoApi.modelo,
            func.sum(ConsumoApi.custo_brl).label("gasto_brl"),
            func.sum(ConsumoApi.tokens_prompt + ConsumoApi.tokens_saida).label("tokens_total"),
            func.count(ConsumoApi.id).label("chamadas"),
        )
        .where(ConsumoApi.timestamp >= inicio)
        .group_by(ConsumoApi.modelo)
        .order_by(func.sum(ConsumoApi.custo_brl).desc())
    )
    rows = result.all()

    return [
        {
            "modelo": r.modelo,
            "gasto_brl": round(float(r.gasto_brl), 4),
            "tokens_total": int(r.tokens_total),
            "chamadas": int(r.chamadas),
        }
        for r in rows
    ]
