"""
Escrivão AI — API: Copiloto Investigativo
Endpoints para sessões de chat e interação conversacional RAG.
Conforme blueprint §7 (Copiloto Investigativo).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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
        db=db,
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


@router.post("/chat/{sessao_id}/com-anexo", response_model=MensagemResponse)
async def enviar_mensagem_com_anexo(
    sessao_id: uuid.UUID,
    mensagem: str = Form(...),
    auditar: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Envia mensagem ao copiloto com um arquivo anexado (PDF, TXT, imagem).
    O texto é extraído do arquivo e injetado no contexto da conversa.
    """
    # Buscar sessão e inquérito
    result = await db.execute(select(SessaoChat).where(SessaoChat.id == sessao_id))
    sessao = result.scalar_one_or_none()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not sessao.ativa:
        raise HTTPException(status_code=400, detail="Sessão encerrada")

    result = await db.execute(select(Inquerito).where(Inquerito.id == sessao.inquerito_id))
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    # ── Extrair texto do arquivo ──────────────────────────────────────────────
    content = await file.read()
    nome_arquivo = file.filename or "anexo"
    texto_extraido = ""

    ext = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""

    if ext == "pdf":
        try:
            from app.services.pdf_extractor import PDFExtractorService
            pdf_svc = PDFExtractorService()
            extraction = pdf_svc.extract_with_ocr(content)
            texto_extraido = extraction.get("texto_completo", "")
            logger.info(f"[COPILOTO-ANEXO] PDF extraído: {len(texto_extraido)} chars")
        except Exception as e:
            logger.warning(f"[COPILOTO-ANEXO] Falha ao extrair PDF: {e}")
            raise HTTPException(status_code=422, detail=f"Não foi possível extrair texto do PDF: {e}")

    elif ext in ("txt", "md", "csv"):
        try:
            texto_extraido = content.decode("utf-8", errors="replace")
        except Exception:
            texto_extraido = content.decode("latin-1", errors="replace")

    elif ext in ("png", "jpg", "jpeg", "tiff", "tif", "webp"):
        # Para imagens, usa Gemini Vision para descrever/transcrever
        try:
            import base64
            import httpx
            from app.core.config import settings as _s
            img_b64 = base64.b64encode(content).decode()
            mime = file.content_type or f"image/{ext}"
            resp = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{_s.LLM_STANDARD_MODEL}:generateContent",
                params={"key": _s.GEMINI_API_KEY},
                json={
                    "contents": [{
                        "parts": [
                            {"inline_data": {"mime_type": mime, "data": img_b64}},
                            {"text": "Transcreva todo o texto visível nesta imagem, mantendo a formatação original. Se for um documento, preserva a estrutura (cabeçalhos, listas, parágrafos). Se não houver texto, descreva o conteúdo em detalhes."}
                        ]
                    }],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            texto_extraido = (
                resp.json().get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            logger.info(f"[COPILOTO-ANEXO] Imagem transcrita via Gemini Vision: {len(texto_extraido)} chars")
        except Exception as e:
            logger.warning(f"[COPILOTO-ANEXO] Falha ao transcrever imagem: {e}")
            raise HTTPException(status_code=422, detail=f"Não foi possível processar a imagem: {e}")
    else:
        raise HTTPException(
            status_code=415,
            detail=f"Formato '{ext}' não suportado. Use PDF, TXT, PNG, JPG ou TIFF."
        )

    if not texto_extraido.strip():
        raise HTTPException(status_code=422, detail="O arquivo não contém texto legível.")

    # ── Salvar mensagem do usuário com indicação do anexo ────────────────────
    msg_usuario = MensagemChat(
        sessao_id=sessao.id,
        role="user",
        conteudo=f"[Anexo: {nome_arquivo}]\n{mensagem}",
    )
    db.add(msg_usuario)

    # Histórico
    result = await db.execute(
        select(MensagemChat)
        .where(MensagemChat.sessao_id == sessao.id)
        .order_by(MensagemChat.created_at)
    )
    mensagens_anteriores = result.scalars().all()
    historico = [{"role": m.role, "content": m.conteudo} for m in mensagens_anteriores]

    # ── Processar com copiloto ────────────────────────────────────────────────
    from app.services.copiloto_service import CopilotoService
    copiloto = CopilotoService()

    resultado = await copiloto.processar_mensagem(
        query=mensagem,
        inquerito_id=str(sessao.inquerito_id),
        historico=historico,
        numero_inquerito=inquerito.numero,
        estado_atual=inquerito.estado_atual,
        total_paginas=inquerito.total_paginas,
        total_documentos=inquerito.total_documentos,
        auditar=auditar,
        db=db,
        texto_anexo=texto_extraido,
        nome_anexo=nome_arquivo,
    )

    # Salvar resposta
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
    sessao.total_mensagens += 2
    sessao.total_tokens += resultado["tokens_prompt"] + resultado["tokens_resposta"]
    await db.flush()

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
