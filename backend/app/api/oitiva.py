"""
Escrivão AI — API: Modo Oitiva
Endpoint para transcrição e lavração automática de termos de oitiva.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/oitiva", tags=["Modo Oitiva"])


class OitivaRequest(BaseModel):
    transcricao: str
    data_hora: str = ""
    local: str = ""
    comissario: str = ""
    qualificacao: str = ""
    papel: str = "testemunha"


@router.post("/transcrever", summary="Transcreve áudio de oitiva para texto")
async def transcrever_oitiva(audio: UploadFile = File(...)):
    """
    Transcreve o áudio de uma oitiva policial (gravação longa, até ~1h).
    Retorna a transcrição bruta que pode ser enviada para /lavrar.
    """
    from google import genai as _genai
    from google.genai import types as _genai_types
    from app.core.config import settings

    audio_bytes = await audio.read()
    filename = audio.filename or "oitiva.webm"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
    mime_map = {
        "ogg": "audio/ogg", "mp3": "audio/mpeg", "m4a": "audio/mp4",
        "wav": "audio/wav", "mp4": "video/mp4", "webm": "audio/webm",
    }
    mime = mime_map.get(ext, "audio/webm")

    try:
        client = _genai.Client(api_key=settings.GEMINI_API_KEY)
        part = _genai_types.Part.from_bytes(data=audio_bytes, mime_type=mime)
        response = await client.aio.models.generate_content(
            model=settings.LLM_STANDARD_MODEL,
            contents=[
                "Transcreva fielmente TODA a conversa neste áudio em português. "
                "Separe as falas por linha. Se conseguir identificar quem está falando "
                "(pergunta vs resposta), prefixe com 'COMISSÁRIO:' ou 'DECLARANTE:'. "
                "Retorne apenas a transcrição, sem comentários.",
                part,
            ],
        )
        return {"transcricao": response.text.strip(), "tamanho_bytes": len(audio_bytes)}
    except Exception as e:
        logger.error(f"[OITIVA] Erro na transcrição: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro na transcrição: {str(e)[:300]}")


@router.post("/lavrar", summary="Converte transcrição em Termo de Oitiva formal")
async def lavrar_termo(body: OitivaRequest):
    """
    Recebe transcrição bruta e dados do ato.
    Retorna o Termo de Oitiva no padrão formal da Polícia Civil.
    """
    from app.core.prompts import PROMPT_OITIVA
    from app.services.llm_service import LLMService

    if len(body.transcricao) < 50:
        raise HTTPException(status_code=422, detail="Transcrição muito curta para lavrar o termo.")

    data_hora = body.data_hora or datetime.now().strftime("%d/%m/%Y às %H:%M")

    prompt = PROMPT_OITIVA.format(
        transcricao=body.transcricao,
        data_hora=data_hora,
        local=body.local or "[local não informado]",
        comissario=body.comissario or "[Comissário não identificado]",
        qualificacao=body.qualificacao or "[qualificação a completar]",
        papel=body.papel,
    )

    llm = LLMService()
    try:
        result = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="premium",
            temperature=0.05,
            max_tokens=8000,
            agente="Oitiva",
        )
        termo = result["content"].strip()
        return {
            "termo": termo,
            "modelo": result.get("model"),
            "chars": len(termo),
        }
    except Exception as e:
        logger.error(f"[OITIVA] Erro ao lavrar termo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar o termo: {str(e)[:300]}")
