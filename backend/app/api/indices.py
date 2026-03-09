"""
Escrivão AI — API: Índices Investigativos
Endpoints para retornar pessoas, empresas, enderecos, contatos e cronologia extraídos dos documentos de um inquérito.
Conforme blueprint §13.2 (Consultas estruturadas).
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.pessoa import Pessoa
from app.models.empresa import Empresa
from app.models.endereco import Endereco
from app.models.contato import Contato
from app.models.evento_cronologico import EventoCronologico
from app.schemas.indices import (
    PessoaOut, EmpresaOut, EnderecoOut, ContatoOut, EventoCronologicoOut
)

router = APIRouter(prefix="/api/v1/inqueritos/{inquerito_id}/indices", tags=["Indices"])

@router.get("/pessoas", response_model=List[PessoaOut])
async def listar_pessoas(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retorna pessoas identificadas no inquérito."""
    result = await db.execute(
        select(Pessoa)
        .where(Pessoa.inquerito_id == inquerito_id)
        .order_by(Pessoa.nome)
    )
    return result.scalars().all()

@router.get("/empresas", response_model=List[EmpresaOut])
async def listar_empresas(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retorna empresas identificadas no inquérito."""
    result = await db.execute(
        select(Empresa)
        .where(Empresa.inquerito_id == inquerito_id)
        .order_by(Empresa.nome)
    )
    return result.scalars().all()

@router.get("/enderecos", response_model=List[EnderecoOut])
async def listar_enderecos(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retorna endereços citados no inquérito."""
    result = await db.execute(
        select(Endereco)
        .where(Endereco.inquerito_id == inquerito_id)
    )
    return result.scalars().all()

@router.get("/contatos", response_model=List[ContatoOut])
async def listar_contatos(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retorna telefones e e-mails extraídos."""
    result = await db.execute(
        select(Contato)
        .where(Contato.inquerito_id == inquerito_id)
    )
    return result.scalars().all()

@router.get("/cronologia", response_model=List[EventoCronologicoOut])
async def listar_cronologia(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retorna a linha do tempo extraída do inquérito."""
    result = await db.execute(
        select(EventoCronologico)
        .where(EventoCronologico.inquerito_id == inquerito_id)
        # TODO: melhor sort logic mixando data_fato e data_fato_str
    )
    return result.scalars().all()
