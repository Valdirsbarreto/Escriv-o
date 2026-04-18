"""
Escrivão AI — API: Chat do Agente Web
Endpoint para o widget de chat web usando CopilotoService (RAG completo).
Substituiu TelegramCopilotoService que requeria Gemini Function Calling (403 no projeto).
"""

import json
import logging
import re
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.inquerito import Inquerito

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agente Chat Web"])

_copiloto = None
_redis = None


def _get_copiloto():
    global _copiloto
    if _copiloto is None:
        from app.services.copiloto_service import CopilotoService
        _copiloto = CopilotoService()
    return _copiloto


async def _get_redis():
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _check_auth(x_chat_secret: str) -> None:
    if settings.APP_ENV == "production" and x_chat_secret != settings.APP_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Acesso não autorizado")


# ── Schemas ────────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    mensagem: str
    session_id: str
    inquerito_id: Optional[str] = None


class ChatResponse(BaseModel):
    resposta: str


class SetInqueritoRequest(BaseModel):
    session_id: str
    inquerito_id: str


# ── Helpers de contexto Redis ──────────────────────────────────────────────────


async def _load_ctx(session_id: str) -> dict:
    r = await _get_redis()
    raw = await r.get(f"agente_web:ctx:{session_id}")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {"historico": [], "inquerito_id": None, "inquerito_numero": None,
            "estado_atual": "", "total_documentos": 0, "total_paginas": 0}


async def _save_ctx(session_id: str, ctx: dict) -> None:
    r = await _get_redis()
    await r.setex(
        f"agente_web:ctx:{session_id}",
        86400,
        json.dumps(ctx, ensure_ascii=False, default=str),
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(
    body: ChatRequest,
    x_chat_secret: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Chat com o Copiloto RAG (CopilotoService — sem Function Calling).
    Contexto: documentos gerados + RAG híbrido + histórico de sessão.
    """
    _check_auth(x_chat_secret)

    if not body.mensagem.strip():
        raise HTTPException(status_code=422, detail="Mensagem não pode ser vazia")

    ctx = await _load_ctx(body.session_id)

    # Atualizar inquérito no contexto se fornecido
    if body.inquerito_id and body.inquerito_id != ctx.get("inquerito_id"):
        await _sync_inquerito_context(body.session_id, body.inquerito_id, db, ctx)

    inquerito_id = ctx.get("inquerito_id")

    # Sem contexto: tenta resolver o IP pelo número mencionado na mensagem
    if not inquerito_id:
        ip = await _resolver_inquerito_por_mensagem(body.mensagem, db)
        if ip:
            await _sync_inquerito_context(body.session_id, str(ip.id), db, ctx)
            inquerito_id = str(ip.id)
            logger.info(f"[AGENT-CHAT] IP resolvido por texto: {ip.numero}")
        else:
            res = await db.execute(
                select(Inquerito.numero, Inquerito.descricao)
                .order_by(Inquerito.updated_at.desc())
                .limit(8)
            )
            ips = res.all()
            if ips:
                lista = "\n".join(
                    f"• {r.numero}" + (f" — {r.descricao[:60]}" if r.descricao else "")
                    for r in ips
                )
                return ChatResponse(
                    resposta=f"Qual inquérito, Comissário? Informe o número do IP.\n\nIPs disponíveis:\n{lista}"
                )
            return ChatResponse(
                resposta="Nenhum inquérito encontrado. Importe os autos pela aba Importar."
            )

    try:
        resultado = await _get_copiloto().processar_mensagem(
            query=body.mensagem,
            inquerito_id=inquerito_id,
            historico=ctx.get("historico", []),
            numero_inquerito=ctx.get("inquerito_numero", ""),
            estado_atual=ctx.get("estado_atual", ""),
            total_documentos=ctx.get("total_documentos", 0),
            total_paginas=ctx.get("total_paginas", 0),
            auditar=False,  # auditoria desabilitada no chat web para latência menor
            db=db,
        )
    except Exception as e:
        logger.error(f"[AGENT-CHAT] Erro ao processar mensagem: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao processar mensagem")

    resposta = resultado.get("resposta", "Não consegui processar. Tente novamente.")

    # Atualizar histórico
    historico = ctx.get("historico", [])
    historico.append({"role": "user", "content": body.mensagem[:300]})
    historico.append({"role": "model", "content": resposta[:500]})
    if len(historico) > 20:
        historico = historico[-20:]
    ctx["historico"] = historico
    await _save_ctx(body.session_id, ctx)

    return ChatResponse(resposta=resposta)


@router.post("/chat/set-inquerito")
async def set_inquerito_context(
    body: SetInqueritoRequest,
    x_chat_secret: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Define o inquérito em foco no contexto da sessão web."""
    _check_auth(x_chat_secret)
    ctx = await _load_ctx(body.session_id)
    numero = await _sync_inquerito_context(body.session_id, body.inquerito_id, db, ctx)
    return {"ok": True, "inquerito_atual": numero}


@router.delete("/chat/context")
async def clear_context(
    session_id: str,
    x_chat_secret: str = Header(default=""),
):
    """Limpa o contexto Redis da sessão web."""
    _check_auth(x_chat_secret)
    r = await _get_redis()
    await r.delete(f"agente_web:ctx:{session_id}")
    return {"ok": True}


# ── Helper ─────────────────────────────────────────────────────────────────────


async def _resolver_inquerito_por_mensagem(mensagem: str, db: AsyncSession) -> Optional[Inquerito]:
    """
    Extrai número de inquérito da mensagem e busca no banco.
    Tenta padrões do mais específico para o menos específico.
    """
    padroes = [
        r'\d{3}[-.]?\d{5}[-/]\d{4}',   # 911-00209/2019 ou 911.00209.2019
        r'\d{3}[-.]?\d{5}',             # 911-00209
        r'\d{5}[-/]\d{4}',              # 00209/2019
        r'\b0+\d{3,5}\b',               # 00209, 0209
        r'\b\d{3,5}\b',                 # 209, 2280
    ]
    for padrao in padroes:
        for match in re.findall(padrao, mensagem):
            termo = re.sub(r'[-./]', '', match)  # normaliza para busca
            result = await db.execute(
                select(Inquerito).where(Inquerito.numero.ilike(f"%{termo}%"))
            )
            ip = result.scalars().first()
            if ip:
                return ip
    return None


async def _sync_inquerito_context(
    session_id: str, inquerito_id: str, db: AsyncSession, ctx: dict
) -> str:
    result = await db.execute(select(Inquerito).where(Inquerito.id == inquerito_id))
    ip = result.scalars().first()
    if not ip:
        return ""
    ctx["inquerito_id"] = str(ip.id)
    ctx["inquerito_numero"] = ip.numero
    ctx["estado_atual"] = ip.estado_atual or ""
    ctx["total_documentos"] = ip.total_documentos or 0
    ctx["total_paginas"] = ip.total_paginas or 0
    await _save_ctx(session_id, ctx)
    return ip.numero
