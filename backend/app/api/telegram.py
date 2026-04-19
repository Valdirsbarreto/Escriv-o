"""
Escrivão AI — API: Telegram Bot Webhook
Recebe updates do Telegram, autentica e despacha para o TelegramCopilotoService.
"""

import io
import logging
import re
import struct
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram Bot"])


async def _transcrever_audio(audio_bytes: bytes, file_path: str) -> str:
    """Transcreve áudio de voz usando Gemini Vision (suporta OGG/MP3/M4A)."""
    from google import genai as _genai
    from google.genai import types as _genai_types
    from app.core.config import settings as _s

    client = _genai.Client(api_key=_s.GEMINI_API_KEY)
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "ogg"
    mime_map = {"ogg": "audio/ogg", "mp3": "audio/mp3", "m4a": "audio/mp4", "wav": "audio/wav", "mp4": "video/mp4"}
    mime = mime_map.get(ext, "audio/ogg")

    part = _genai_types.Part.from_bytes(data=audio_bytes, mime_type=mime)
    response = await client.aio.models.generate_content(
        model=settings.LLM_STANDARD_MODEL,  # gemini-2.5-flash
        contents=[
            "Transcreva fielmente o que foi dito neste áudio em português. Retorne apenas a transcrição, sem comentários.",
            part,
        ],
    )
    return response.text.strip()

def _pcm_para_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Empacota PCM16 bruto em container WAV (sem dependências externas)."""
    n_canais, sample_width = 1, 2
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(pcm_data)))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))  # PCM
    buf.write(struct.pack("<H", n_canais))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * n_canais * sample_width))
    buf.write(struct.pack("<H", n_canais * sample_width))
    buf.write(struct.pack("<H", sample_width * 8))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(pcm_data)))
    buf.write(pcm_data)
    return buf.getvalue()


async def _resumir_para_voz(texto_html: str) -> str:
    """
    Converte resposta escrita (HTML, detalhada) em 1-3 frases naturais para voz.
    Usa Flash Lite (barato) para resumo conversacional.
    Regra principal: se for confirmação de contexto de inquérito, diz o número e pergunta como pode ajudar.
    """
    # Remove HTML
    texto_limpo = re.sub(r"<[^>]+>", " ", texto_html)
    texto_limpo = re.sub(r"&\w+;", " ", texto_limpo)
    texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()

    # Se o texto já for curto (≤ 200 chars), usa diretamente
    if len(texto_limpo) <= 200:
        return texto_limpo

    try:
        from google import genai as _genai

        client = _genai.Client(api_key=settings.GEMINI_API_KEY)
        response = await client.aio.models.generate_content(
            model=settings.LLM_ECONOMICO_MODEL,  # gemini-2.5-flash-lite
            contents=(
                "Você é um assistente de voz policial. "
                "Transforme o texto abaixo em 1 a 3 frases curtas e naturais para serem FALADAS em voz alta.\n"
                "Regras:\n"
                "- Não mencione formatação, tags, listas, referências de folhas\n"
                "- Não diga o número do inquérito nem que o contexto foi carregado — vá direto ao ponto\n"
                "- Para respostas analíticas, destaque apenas a conclusão principal\n"
                "- Tom direto, como se estivesse falando com o Comissário\n"
                "- Responda SOMENTE com o texto a ser falado, sem aspas, sem comentários\n\n"
                f"TEXTO:\n{texto_limpo[:2000]}"
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.warning(f"[TELEGRAM] Resumo TTS falhou: {e}")
        # Fallback: primeira frase limpa
        match = re.search(r"[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][^.!?]{15,180}[.!?]", texto_limpo)
        return match.group(0) if match else texto_limpo[:250]


async def _gerar_audio_tts(texto_para_falar: str) -> Optional[bytes]:
    """
    Gera áudio TTS via Gemini 2.5 Flash TTS.
    Recebe texto já pronto para voz (sem HTML, curto e conversacional).
    Retorna WAV bytes ou None se falhar.
    """
    try:
        from google import genai as _genai
        from google.genai import types as _genai_types

        texto = texto_para_falar.strip()
        if not texto:
            return None

        client = _genai.Client(api_key=settings.GEMINI_API_KEY)
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=texto,
            config=_genai_types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=_genai_types.SpeechConfig(
                    voice_config=_genai_types.VoiceConfig(
                        prebuilt_voice_config=_genai_types.PrebuiltVoiceConfig(
                            voice_name="Charon",
                        )
                    )
                ),
            ),
        )
        pcm_data = response.candidates[0].content.parts[0].inline_data.data
        if isinstance(pcm_data, str):
            import base64
            pcm_data = base64.b64decode(pcm_data)
        return _pcm_para_wav(pcm_data)
    except Exception as e:
        logger.warning(f"[TELEGRAM] TTS falhou: {e}")
        return None


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
    voice = message.get("voice") or message.get("audio") or message.get("video_note")
    era_voz: bool = bool(voice)

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

    # Se o usuário enviou um áudio, responder também em áudio (TTS)
    if era_voz:
        await _get_bot().send_chat_action(chat_id, "upload_voice")
        texto_voz = await _resumir_para_voz(resposta)
        logger.info(f"[TELEGRAM] TTS texto: {texto_voz[:120]}")
        audio_bytes = await _gerar_audio_tts(texto_voz)
        if audio_bytes:
            r = await _get_bot().send_audio(chat_id, audio_bytes)
            if not r.get("ok"):
                logger.warning(f"[TELEGRAM] TTS sendAudio falhou, usando sendVoice: {r.get('description')}")
                await _get_bot().send_voice(chat_id, audio_bytes)

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
