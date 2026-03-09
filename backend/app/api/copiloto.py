"""
Escrivão AI — API: Copiloto Investigativo
Endpoints para sessões de chat e interação conversacional RAG.
Conforme blueprint §7 (Copiloto Investigativo).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.inquerito import Inquerito
from app.models.sessao_chat import SessaoChat
from app.models.mensagem_chat import MensagemChat
from app.schemas.chat import (
    SessaoChatCreate,
    SessaoChatResponse,
    MensagemRequest,
    MensagemResponse,
    MensagemChatResponse,
    HistoricoResponse,
    FonteCitada,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copiloto", tags=["Copiloto Investigativo"])


# ── Sessões ───────────────────────────────────────────────


@router.post("/sessoes", response_model=SessaoChatResponse, status_code=201)
async def criar_sessao(
    dados: SessaoChatCreate,
    db: AsyncSession = Depends(get_db),
):
    """Cria uma nova sessão de chat com o copiloto."""
    # Verificar inquérito
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == dados.inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    sessao = SessaoChat(
        inquerito_id=dados.inquerito_id,
        contexto=dados.contexto,
        titulo=dados.titulo or f"Chat - {inquerito.numero}",
    )
    db.add(sessao)
    await db.flush()
    await db.refresh(sessao)
    return sessao


@router.get("/sessoes/{inquerito_id}", response_model=list[SessaoChatResponse])
async def listar_sessoes(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Lista sessões de chat de um inquérito."""
    result = await db.execute(
        select(SessaoChat)
        .where(SessaoChat.inquerito_id == inquerito_id)
        .order_by(SessaoChat.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/sessoes/{sessao_id}/historico", response_model=HistoricoResponse)
async def obter_historico(
    sessao_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retorna o histórico completo de uma sessão."""
    result = await db.execute(
        select(SessaoChat)
        .options(selectinload(SessaoChat.mensagens))
        .where(SessaoChat.id == sessao_id)
    )
    sessao = result.scalar_one_or_none()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    return HistoricoResponse(sessao=sessao, mensagens=sessao.mensagens)


# ── Chat / Envio de Mensagens ─────────────────────────────


@router.post("/chat/{sessao_id}", response_model=MensagemResponse)
async def enviar_mensagem(
    sessao_id: uuid.UUID,
    dados: MensagemRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Envia uma mensagem ao copiloto e recebe resposta com fontes.

    Pipeline RAG:
    1. Busca chunks relevantes no Qdrant
    2. Monta contexto com citações
    3. Envia para LLM premium
    4. Audita factualmente (opcional)
    5. Retorna resposta com fontes e auditoria
    """
    # Buscar sessão
    result = await db.execute(
        select(SessaoChat).where(SessaoChat.id == sessao_id)
    )
    sessao = result.scalar_one_or_none()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    if not sessao.ativa:
        raise HTTPException(status_code=400, detail="Sessão encerrada")

    # Buscar inquérito
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == sessao.inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    # Salvar mensagem do usuário
    msg_usuario = MensagemChat(
        sessao_id=sessao.id,
        role="user",
        conteudo=dados.mensagem,
    )
    db.add(msg_usuario)

    # Buscar histórico recente para contexto
    result = await db.execute(
        select(MensagemChat)
        .where(MensagemChat.sessao_id == sessao.id)
        .order_by(MensagemChat.created_at)
    )
    mensagens_anteriores = result.scalars().all()
    historico = [
        {"role": m.role, "content": m.conteudo}
        for m in mensagens_anteriores
    ]

    # Processar com o copiloto
    from app.services.copiloto_service import CopilotoService
    copiloto = CopilotoService()

    resultado = await copiloto.processar_mensagem(
        query=dados.mensagem,
        inquerito_id=str(sessao.inquerito_id),
        historico=historico,
        numero_inquerito=inquerito.numero,
        estado_atual=inquerito.estado_atual,
        total_paginas=inquerito.total_paginas,
        total_documentos=inquerito.total_documentos,
        auditar=dados.auditar,
    )

    # Salvar resposta do assistente
    msg_assistente = MensagemChat(
        sessao_id=sessao.id,
        role="assistant",
        conteudo=resultado["resposta"],
        fontes={"fontes": resultado["fontes"], "auditoria": resultado.get("auditoria")},
        modelo_utilizado=resultado["modelo"],
        tokens_prompt=resultado["tokens_prompt"],
        tokens_resposta=resultado["tokens_resposta"],
        custo_estimado=resultado["custo_estimado"],
        tempo_resposta_ms=resultado["tempo_total_ms"],
    )
    db.add(msg_assistente)

    # Atualizar contadores da sessão
    sessao.total_mensagens += 2
    sessao.total_tokens += resultado["tokens_prompt"] + resultado["tokens_resposta"]

    await db.flush()

    # Formatar resposta
    fontes_formatadas = [
        FonteCitada(
            documento_id=f.get("documento_id", ""),
            pagina_inicial=f.get("pagina_inicial", 0),
            pagina_final=f.get("pagina_final", 0),
            score=f.get("score", 0.0),
            tipo_documento=f.get("tipo_documento", ""),
        )
        for f in resultado["fontes"]
    ]

    return MensagemResponse(
        resposta=resultado["resposta"],
        fontes=fontes_formatadas,
        auditoria=resultado.get("auditoria"),
        modelo=resultado["modelo"],
        tokens_prompt=resultado["tokens_prompt"],
        tokens_resposta=resultado["tokens_resposta"],
        custo_estimado=resultado["custo_estimado"],
        tempo_total_ms=resultado["tempo_total_ms"],
    )


@router.post("/chat/{sessao_id}/encerrar", response_model=SessaoChatResponse)
async def encerrar_sessao(
    sessao_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Encerra uma sessão de chat."""
    result = await db.execute(
        select(SessaoChat).where(SessaoChat.id == sessao_id)
    )
    sessao = result.scalar_one_or_none()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    sessao.ativa = False
    await db.flush()
    await db.refresh(sessao)
    return sessao
