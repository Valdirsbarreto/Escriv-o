"""
Escrivão AI — API: Telegram Bot Webhook
Recebe updates do Telegram, autentica e despacha para o TelegramCopilotoService.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram Bot"])


async def _transcrever_audio(audio_bytes: bytes, file_path: str) -> str:
    """Transcreve áudio de voz usando Gemini Vision (suporta OGG/MP3/M4A)."""
    import base64
    import google.generativeai as genai
    from app.core.config import settings as _s

    if _s.GEMINI_API_KEY:
        genai.configure(api_key=_s.GEMINI_API_KEY)

    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "ogg"
    mime_map = {"ogg": "audio/ogg", "mp3": "audio/mp3", "m4a": "audio/mp4", "wav": "audio/wav"}
    mime = mime_map.get(ext, "audio/ogg")

    model = genai.GenerativeModel("gemini-2.0-flash")
    part = {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio_bytes).decode()}}
    response = model.generate_content([
        "Transcreva fielmente o que foi dito neste áudio em português. Retorne apenas a transcrição, sem comentários.",
        part,
    ])
    return response.text.strip()

_bot = None
_copiloto = None


def _get_bot():
    global _bot
    if _bot is None:
        from app.services.telegram_bot import TelegramBotService
        _bot = TelegramBotService()
    return _bot


def _get_copiloto():
    global _copiloto
    if _copiloto is None:
        from app.services.telegram_copiloto import TelegramCopilotoService
        _copiloto = TelegramCopilotoService()
    return _copiloto


def _allowed_user_ids() -> set[int]:
    """Retorna conjunto de user_ids autorizados (vazio = todos bloqueados)."""
    raw = settings.TELEGRAM_ALLOWED_USER_IDS.strip()
    if not raw:
        return set()
    result = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result


# ── Webhook principal ─────────────────────────────────────────────────────────


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe updates do Telegram via webhook.

    Segurança:
    - Verifica X-Telegram-Bot-Api-Secret-Token se TELEGRAM_WEBHOOK_SECRET estiver configurado
    - Aceita apenas user_ids listados em TELEGRAM_ALLOWED_USER_IDS
    """
    # Verificar secret token no header (recomendado em produção)
    if settings.TELEGRAM_WEBHOOK_SECRET:
        header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_token != settings.TELEGRAM_WEBHOOK_SECRET:
            logger.warning("[TELEGRAM] Webhook recebido com token inválido")
            raise HTTPException(status_code=403, detail="Token inválido")

    body = await request.json()

    # Suportar mensagens normais e edições
    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}  # Ignorar outros tipos de update (inline, callback, etc.)

    chat_id: int = message.get("chat", {}).get("id")
    user_id: int = message.get("from", {}).get("id")
    text: str = (message.get("text") or "").strip()
    voice = message.get("voice") or message.get("audio")

    if not chat_id:
        return {"ok": True}

    # Transcrever áudio se não houver texto
    if not text and voice:
        file_id = voice.get("file_id")
        if file_id:
            try:
                await _get_bot().send_chat_action(chat_id, "typing")
                file_meta = await _get_bot().get_file(file_id)
                file_path = file_meta.get("result", {}).get("file_path", "")
                if file_path:
                    audio_bytes = await _get_bot().download_file(file_path)
                    text = await _transcrever_audio(audio_bytes, file_path)
                    logger.info(f"[TELEGRAM] Áudio transcrito: {text[:100]}")
                else:
                    logger.warning(f"[TELEGRAM] file_path vazio para file_id={file_id}. Resposta: {file_meta}")
                    await _get_bot().send_message(chat_id, "⚠️ Não consegui baixar o áudio. Tente novamente ou envie como texto.")
                    return {"ok": True}
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro ao transcrever áudio: {e}", exc_info=True)
                await _get_bot().send_message(chat_id, f"⚠️ Erro ao transcrever áudio: {type(e).__name__}. Tente enviar como texto.")
                return {"ok": True}

    if not text:
        return {"ok": True}

    # Autenticação por user_id
    allowed = _allowed_user_ids()
    if allowed and user_id not in allowed:
        logger.warning(f"[TELEGRAM] Acesso negado — user_id={user_id}")
        await _get_bot().send_message(chat_id, "⛔ Acesso não autorizado.")
        return {"ok": True}

    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("[TELEGRAM] TELEGRAM_BOT_TOKEN não configurado")
        return {"ok": True}

    # Indicador "digitando..." enquanto processa
    await _get_bot().send_chat_action(chat_id, "typing")

    # Processar e responder
    try:
        resposta = await _get_copiloto().processar_mensagem(
            chat_id=chat_id,
            mensagem=text,
            db=db,
        )
    except Exception as e:
        logger.error(f"[TELEGRAM] Erro ao processar mensagem: {e}", exc_info=True)
        resposta = "⚠️ Erro interno. Tente novamente ou acesse a interface web."

    await _get_bot().send_message(chat_id, resposta)
    return {"ok": True}


# ── Utilitários de gestão ─────────────────────────────────────────────────────


@router.post("/configurar-webhook", summary="Registra webhook no Telegram")
async def configurar_webhook(base_url: str):
    """
    Registra a URL de webhook no Telegram.
    Chamar após cada deploy com a URL pública do servidor.

    Exemplo: POST /api/v1/telegram/configurar-webhook?base_url=https://meu-app.railway.app
    """
    webhook_url = f"{base_url.rstrip('/')}/api/v1/telegram/webhook"
    result = await _get_bot().set_webhook(webhook_url, settings.TELEGRAM_WEBHOOK_SECRET)
    return {"webhook_url": webhook_url, "telegram_response": result}


@router.delete("/webhook", summary="Remove o webhook (voltar ao polling)")
async def remover_webhook():
    """Remove o webhook configurado. Útil em desenvolvimento."""
    result = await _get_bot().delete_webhook()
    return {"telegram_response": result}


@router.get("/status", summary="Verifica status do bot")
async def status_bot():
    """Retorna informações do bot e configuração atual."""
    configured = bool(settings.TELEGRAM_BOT_TOKEN)
    allowed = list(_allowed_user_ids())

    bot_info = {}
    if configured:
        try:
            bot_info = await _get_bot().get_me()
        except Exception as e:
            bot_info = {"error": str(e)}

    return {
        "configured": configured,
        "allowed_user_ids": allowed,
        "webhook_secret_set": bool(settings.TELEGRAM_WEBHOOK_SECRET),
        "bot_info": bot_info.get("result", {}),
    }
