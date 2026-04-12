"""
Escrivão AI — API de Peças Extraídas
Endpoints para listar e visualizar peças individuais extraídas dos PDFs pela IA.
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.peca_extraida import PecaExtraida
from app.models.documento import Documento

router = APIRouter(tags=["Peças Extraídas"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class PecaListItem(BaseModel):
    id: str
    inquerito_id: str
    documento_id: str
    documento_nome: Optional[str] = None
    titulo: str
    tipo: str
    pagina_inicial: Optional[int] = None
    pagina_final: Optional[int] = None
    resumo: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


class PecaResponse(PecaListItem):
    conteudo_texto: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/inqueritos/{inquerito_id}/pecas-extraidas", response_model=List[PecaListItem])
async def listar_pecas(
    inquerito_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Lista todas as peças extraídas do inquérito (sem conteúdo completo)."""
    result = await db.execute(
        select(PecaExtraida, Documento.nome_arquivo)
        .join(Documento, PecaExtraida.documento_id == Documento.id, isouter=True)
        .where(PecaExtraida.inquerito_id == uuid.UUID(inquerito_id))
        .order_by(PecaExtraida.created_at.asc())
    )
    rows = result.all()
    return [
        PecaListItem(
            id=str(peca.id),
            inquerito_id=str(peca.inquerito_id),
            documento_id=str(peca.documento_id),
            documento_nome=nome_arquivo,
            titulo=peca.titulo,
            tipo=peca.tipo,
            pagina_inicial=peca.pagina_inicial,
            pagina_final=peca.pagina_final,
            resumo=peca.resumo,
            created_at=peca.created_at.isoformat() if peca.created_at else "",
        )
        for peca, nome_arquivo in rows
    ]


@router.get("/inqueritos/{inquerito_id}/pecas-extraidas/{peca_id}", response_model=PecaResponse)
async def obter_peca(
    inquerito_id: str,
    peca_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retorna uma peça específica com conteúdo completo."""
    result = await db.execute(
        select(PecaExtraida, Documento.nome_arquivo)
        .join(Documento, PecaExtraida.documento_id == Documento.id, isouter=True)
        .where(
            PecaExtraida.id == uuid.UUID(peca_id),
            PecaExtraida.inquerito_id == uuid.UUID(inquerito_id),
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Peça não encontrada.")

    peca, nome_arquivo = row
    return PecaResponse(
        id=str(peca.id),
        inquerito_id=str(peca.inquerito_id),
        documento_id=str(peca.documento_id),
        documento_nome=nome_arquivo,
        titulo=peca.titulo,
        tipo=peca.tipo,
        pagina_inicial=peca.pagina_inicial,
        pagina_final=peca.pagina_final,
        resumo=peca.resumo,
        conteudo_texto=peca.conteudo_texto,
        created_at=peca.created_at.isoformat() if peca.created_at else "",
    )


@router.post("/inqueritos/{inquerito_id}/documentos/{documento_id}/reextrair-pecas", status_code=202)
async def reextrair_pecas(
    inquerito_id: str,
    documento_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Re-dispara a extração de peças para um documento (útil após a primeira ingestão)."""
    # Verifica se o documento pertence ao inquérito
    result = await db.execute(
        select(Documento).where(
            Documento.id == uuid.UUID(documento_id),
            Documento.inquerito_id == uuid.UUID(inquerito_id),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    # Apaga peças existentes para permitir re-extração
    from sqlalchemy import delete
    await db.execute(
        delete(PecaExtraida).where(
            PecaExtraida.documento_id == uuid.UUID(documento_id)
        )
    )
    await db.commit()

    # Dispara task Celery
    from app.workers.peca_extraction_task import extrair_pecas_task
    extrair_pecas_task.delay(documento_id, inquerito_id)

    return {"status": "agendado", "documento_id": documento_id}


@router.post("/inqueritos/{inquerito_id}/reextrair-pecas-lote", status_code=202)
async def reextrair_pecas_lote(
    inquerito_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Dispara extração de peças para todos os documentos indexados do inquérito."""
    from sqlalchemy import delete as sa_delete

    result = await db.execute(
        select(Documento).where(
            Documento.inquerito_id == uuid.UUID(inquerito_id),
            Documento.status_processamento == "concluido",
            Documento.tipo_peca != "sintese_investigativa",
        )
    )
    docs = result.scalars().all()
    if not docs:
        raise HTTPException(status_code=404, detail="Nenhum documento indexado encontrado.")

    from app.workers.peca_extraction_task import extrair_pecas_task

    from sqlalchemy import func

    # Conta peças existentes por documento
    pecas_count_result = await db.execute(
        select(PecaExtraida.documento_id, func.count(PecaExtraida.id).label("total"))
        .where(PecaExtraida.inquerito_id == uuid.UUID(inquerito_id))
        .group_by(PecaExtraida.documento_id)
    )
    docs_com_pecas = {str(row.documento_id) for row in pecas_count_result}

    agendados = []
    pulados = []
    for doc in docs:
        if str(doc.id) in docs_com_pecas:
            pulados.append(str(doc.id))
            continue
        extrair_pecas_task.delay(str(doc.id), inquerito_id)
        agendados.append(str(doc.id))

    return {"status": "agendado", "total": len(agendados), "pulados": len(pulados), "documentos": agendados}
