"""
Escrivão AI — API de Alertas do Sistema
Endpoints para o painel in-app de notificações (AlertasDrawer).
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alerta_log import AlertaLog

router = APIRouter(prefix="/alertas", tags=["Alertas"])


class AlertaResponse(BaseModel):
    id: str
    tipo: str
    nivel: str
    titulo: str
    mensagem: str
    identificador: Optional[str]
    lido: bool
    created_at: str

    @classmethod
    def from_orm(cls, obj: AlertaLog) -> "AlertaResponse":
        return cls(
            id=str(obj.id),
            tipo=obj.tipo,
            nivel=obj.nivel,
            titulo=obj.titulo,
            mensagem=obj.mensagem,
            identificador=obj.identificador,
            lido=obj.lido,
            created_at=obj.created_at.isoformat(),
        )


@router.get("/contagem")
async def contagem_alertas(db: AsyncSession = Depends(get_db)):
    """Retorna contagem de alertas não lidos — usado para polling do badge."""
    result = await db.execute(
        select(func.count(AlertaLog.id)).where(AlertaLog.lido == False)
    )
    nao_lidos = result.scalar() or 0
    return {"nao_lidos": nao_lidos}


@router.get("", response_model=List[AlertaResponse])
async def listar_alertas(db: AsyncSession = Depends(get_db)):
    """Lista alertas não lidos em ordem decrescente de criação (máx 50)."""
    result = await db.execute(
        select(AlertaLog)
        .where(AlertaLog.lido == False)
        .order_by(AlertaLog.created_at.desc())
        .limit(50)
    )
    alertas = result.scalars().all()
    return [AlertaResponse.from_orm(a) for a in alertas]


@router.put("/marcar-todos-lidos")
async def marcar_todos_lidos(db: AsyncSession = Depends(get_db)):
    """Marca todos os alertas não lidos como lidos."""
    await db.execute(
        update(AlertaLog).where(AlertaLog.lido == False).values(lido=True)
    )
    await db.commit()
    return {"ok": True}


@router.delete("")
async def deletar_todos_alertas(db: AsyncSession = Depends(get_db)):
    """Remove permanentemente todos os alertas."""
    await db.execute(delete(AlertaLog))
    await db.commit()
    return {"ok": True}


@router.put("/{alerta_id}/lido")
async def marcar_lido(alerta_id: str, db: AsyncSession = Depends(get_db)):
    """Marca um alerta específico como lido."""
    try:
        alerta_uuid = uuid.UUID(alerta_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID inválido")

    result = await db.execute(
        select(AlertaLog).where(AlertaLog.id == alerta_uuid)
    )
    alerta = result.scalar_one_or_none()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")

    alerta.lido = True
    await db.commit()
    return {"ok": True}
