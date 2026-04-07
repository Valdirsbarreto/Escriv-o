"""
Escrivão AI — API: Chat do Agente Web (Sprint D)
Endpoint para o widget de chat web que reutiliza TelegramCopilotoService.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agente Chat Web"])

_copiloto = None


def _get_copiloto():
    global _copiloto
    if _copiloto is None:
        from app.services.telegram_copiloto import TelegramCopilotoService
        _copiloto = TelegramCopilotoService()
    return _copiloto


def _check_auth(x_chat_secret: str) -> None:
    """Verifica autenticação em produção via APP_SECRET_KEY."""
    if settings.APP_ENV == "production" and x_chat_secret != settings.APP_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Acesso não autorizado")


# ── Schemas ────────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    mensagem: str
    session_id: str          # UUID gerado no frontend e persistido no localStorage
    inquerito_id: Optional[str] = None  # UUID do inquérito ativo (resolve para número internamente)


class ChatResponse(BaseModel):
    resposta: str


class SetInqueritoRequest(BaseModel):
    session_id: str
    inquerito_id: str        # UUID do inquérito


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(
    body: ChatRequest,
    x_chat_secret: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Chat com o agente conversacional completo (Function Calling + RAG + todas as ferramentas).
    Mesmas capacidades do bot Telegram — mesma engine, contexto isolado por session_id.

    Autenticação: header X-Chat-Secret deve conter APP_SECRET_KEY (obrigatório em produção).
    """
    _check_auth(x_chat_secret)

    if not body.mensagem.strip():
        raise HTTPException(status_code=422, detail="Mensagem não pode ser vazia")

    # Se inquerito_id foi fornecido, garantir que está no contexto Redis desta sessão
    if body.inquerito_id:
        await _sync_inquerito_context(body.session_id, body.inquerito_id, db)

    try:
        resposta = await _get_copiloto().processar_mensagem(
            chat_id=f"web_{body.session_id}",
            mensagem=body.mensagem,
            db=db,
        )
    except Exception as e:
        logger.error(f"[AGENT-CHAT] Erro ao processar mensagem: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao processar mensagem")

    return ChatResponse(resposta=resposta)


@router.post("/chat/set-inquerito")
async def set_inquerito_context(
    body: SetInqueritoRequest,
    x_chat_secret: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Define o inquérito em foco no contexto da sessão web.
    Chamado automaticamente quando o usuário abre a página de um inquérito.
    """
    _check_auth(x_chat_secret)

    numero = await _sync_inquerito_context(body.session_id, body.inquerito_id, db)
    return {"ok": True, "inquerito_atual": numero}


@router.delete("/chat/context")
async def clear_context(
    session_id: str,
    x_chat_secret: str = Header(default=""),
):
    """Limpa o contexto Redis da sessão web (nova conversa)."""
    _check_auth(x_chat_secret)

    copiloto = _get_copiloto()
    r = await copiloto._get_redis()
    await r.delete(f"telegram:ctx:web_{session_id}")
    return {"ok": True}


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _sync_inquerito_context(session_id: str, inquerito_id: str, db: AsyncSession) -> str:
    """
    Resolve UUID do inquérito para número e salva em ctx["inquerito_atual"] no Redis.
    Retorna o número do inquérito.
    """
    from app.models.inquerito import Inquerito

    result = await db.execute(select(Inquerito).where(Inquerito.id == inquerito_id))
    ip = result.scalars().first()
    if not ip:
        return ""

    copiloto = _get_copiloto()
    ctx = await copiloto._load_ctx(f"web_{session_id}")
    if ctx.get("inquerito_atual") != ip.numero:
        ctx["inquerito_atual"] = ip.numero
        await copiloto._save_ctx(f"web_{session_id}", ctx)

    return ip.numero
