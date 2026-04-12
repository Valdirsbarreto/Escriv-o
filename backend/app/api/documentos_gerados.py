"""
Escrivão AI — API de Documentos Gerados pela IA
Endpoints para salvar, listar e deletar documentos gerados pelo copiloto.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.documento_gerado import DocumentoGerado

router = APIRouter(tags=["Documentos Gerados"])


# ── Schemas Pydantic ──────────────────────────────────────────────────────────

class DocGeradoCreate(BaseModel):
    titulo: str
    tipo: str = "outro"
    conteudo: str


class DocGeradoResponse(BaseModel):
    id: str
    inquerito_id: str
    titulo: str
    tipo: str
    conteudo: str
    created_at: str

    model_config = {"from_attributes": True}


class DocGeradoListItem(BaseModel):
    id: str
    inquerito_id: str
    titulo: str
    tipo: str
    created_at: str

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/inqueritos/{inquerito_id}/docs-gerados", response_model=List[DocGeradoListItem])
@router.get("/inqueritos/{inquerito_id}/documentos-gerados", response_model=List[DocGeradoListItem], include_in_schema=False)
async def listar_docs_gerados(
    inquerito_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os documentos gerados pela IA para o inquérito (sem conteúdo)."""
    result = await db.execute(
        select(DocumentoGerado)
        .where(DocumentoGerado.inquerito_id == uuid.UUID(inquerito_id))
        .order_by(DocumentoGerado.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        DocGeradoListItem(
            id=str(doc.id),
            inquerito_id=str(doc.inquerito_id),
            titulo=doc.titulo,
            tipo=doc.tipo,
            created_at=doc.created_at.isoformat() if doc.created_at else "",
        )
        for doc in docs
    ]


@router.post("/inqueritos/{inquerito_id}/docs-gerados", response_model=DocGeradoResponse, status_code=201)
async def criar_doc_gerado(
    inquerito_id: str,
    body: DocGeradoCreate,
    db: AsyncSession = Depends(get_db),
):
    """Cria um novo documento gerado pela IA para o inquérito."""
    doc = DocumentoGerado(
        id=uuid.uuid4(),
        inquerito_id=uuid.UUID(inquerito_id),
        titulo=body.titulo,
        tipo=body.tipo,
        conteudo=body.conteudo,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return DocGeradoResponse(
        id=str(doc.id),
        inquerito_id=str(doc.inquerito_id),
        titulo=doc.titulo,
        tipo=doc.tipo,
        conteudo=doc.conteudo,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
    )


@router.get("/inqueritos/{inquerito_id}/docs-gerados/{doc_id}", response_model=DocGeradoResponse)
@router.get("/inqueritos/{inquerito_id}/documentos-gerados/{doc_id}", response_model=DocGeradoResponse, include_in_schema=False)
async def obter_doc_gerado(
    inquerito_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retorna um documento gerado específico com conteúdo completo."""
    result = await db.execute(
        select(DocumentoGerado).where(
            DocumentoGerado.id == uuid.UUID(doc_id),
            DocumentoGerado.inquerito_id == uuid.UUID(inquerito_id),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento gerado não encontrado.")
    return DocGeradoResponse(
        id=str(doc.id),
        inquerito_id=str(doc.inquerito_id),
        titulo=doc.titulo,
        tipo=doc.tipo,
        conteudo=doc.conteudo,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
    )


@router.put("/inqueritos/{inquerito_id}/docs-gerados/{doc_id}", response_model=DocGeradoResponse)
async def atualizar_doc_gerado(
    inquerito_id: str,
    doc_id: str,
    body: DocGeradoCreate,
    db: AsyncSession = Depends(get_db),
):
    """Substitui o conteúdo de um documento gerado existente."""
    result = await db.execute(
        select(DocumentoGerado).where(
            DocumentoGerado.id == uuid.UUID(doc_id),
            DocumentoGerado.inquerito_id == uuid.UUID(inquerito_id),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento gerado não encontrado.")
    doc.titulo = body.titulo
    doc.tipo = body.tipo
    doc.conteudo = body.conteudo
    await db.commit()
    await db.refresh(doc)
    return DocGeradoResponse(
        id=str(doc.id),
        inquerito_id=str(doc.inquerito_id),
        titulo=doc.titulo,
        tipo=doc.tipo,
        conteudo=doc.conteudo,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
    )


@router.delete("/inqueritos/{inquerito_id}/docs-gerados/{doc_id}", status_code=204)
async def deletar_doc_gerado(
    inquerito_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Deleta um documento gerado pela IA."""
    result = await db.execute(
        select(DocumentoGerado).where(
            DocumentoGerado.id == uuid.UUID(doc_id),
            DocumentoGerado.inquerito_id == uuid.UUID(inquerito_id),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento gerado não encontrado.")
    await db.delete(doc)
    await db.commit()
