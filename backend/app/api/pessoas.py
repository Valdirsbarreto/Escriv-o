"""
Escrivão AI — API: Pessoas
Busca global de pessoas através de todos os inquéritos.
"""

import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.pessoa import Pessoa
from app.models.inquerito import Inquerito

router = APIRouter(prefix="/pessoas", tags=["Pessoas"])


@router.get("/buscar")
async def buscar_pessoas_global(
    nome: str = Query(..., min_length=2),
    limit: int = Query(5, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Busca pessoas em todos os inquéritos pelo nome (ILIKE). Usado no Modo Oitiva."""
    stmt = (
        select(Pessoa, Inquerito.numero)
        .join(Inquerito, Pessoa.inquerito_id == Inquerito.id)
        .where(Pessoa.nome.ilike(f"%{nome}%"))
        .order_by(Pessoa.nome)
        .limit(limit)
    )
    rows = await db.execute(stmt)
    return [
        {
            "id": str(p.id),
            "nome": p.nome,
            "tipo_pessoa": p.tipo_pessoa,
            "inquerito_id": str(p.inquerito_id),
            "inquerito_numero": numero,
        }
        for p, numero in rows.all()
    ]
