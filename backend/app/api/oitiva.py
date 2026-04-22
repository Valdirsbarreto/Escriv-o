"""
Escrivão AI — API: Modo Oitiva
Transcrição de áudio, lavração de termo P&R formal, gestão de oitivas gravadas.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/oitiva", tags=["Modo Oitiva"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class LavrarRequest(BaseModel):
    transcricao: str
    papel: str = "testemunha"
    inquerito_id: str
    pessoa_id: Optional[str] = None
    audio_url: Optional[str] = None
    duracao_segundos: Optional[int] = None


class SalvarRequest(BaseModel):
    oitiva_id: str
    termo_com_timestamps: str
    termo_limpo: str
    status: str = "rascunho"  # "rascunho" | "finalizado"
    pessoa_id: Optional[str] = None


class RelavrarBlocoRequest(BaseModel):
    trecho: str
    papel: str = "testemunha"


class AtualizarStatusRequest(BaseModel):
    status: str  # "rascunho" | "finalizado"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_timestamps(texto: str) -> str:
    """Remove marcações [MM:SS] do texto para versão limpa de copiar/colar."""
    return re.sub(r"\[\d{1,2}:\d{2}\]\s*", "", texto).strip()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/transcrever")
async def transcrever_oitiva(audio: UploadFile = File(...)):
    """
    Transcreve áudio de oitiva com timestamps [MM:SS] por turno de fala.
    Retorna transcrição bruta com marcações de tempo + URL do áudio no storage.
    """
    from google import genai as _genai
    from google.genai import types as _genai_types
    from app.core.config import settings
    from app.services.storage import StorageService

    audio_bytes = await audio.read()
    filename = audio.filename or "oitiva.webm"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
    mime_map = {
        "ogg": "audio/ogg", "mp3": "audio/mpeg", "m4a": "audio/mp4",
        "wav": "audio/wav", "mp4": "video/mp4", "webm": "audio/webm",
    }
    mime = mime_map.get(ext, "audio/webm")

    # Upload do áudio para o storage
    audio_url = None
    try:
        storage = StorageService()
        key = f"oitivas/{uuid.uuid4()}.{ext}"
        await storage.upload_file(audio_bytes, key, content_type=mime)
        audio_url = storage.generate_download_url(key, expires_in=86400 * 30)  # 30 dias
    except Exception as e:
        logger.warning(f"[OITIVA] Upload áudio falhou (continuando sem URL): {e}")

    # Transcrição com timestamps
    try:
        client = _genai.Client(api_key=settings.GEMINI_API_KEY)
        part = _genai_types.Part.from_bytes(data=audio_bytes, mime_type=mime)
        response = await client.aio.models.generate_content(
            model=settings.LLM_STANDARD_MODEL,
            contents=[
                (
                    "Transcreva fielmente TODA a conversa neste áudio em português.\n"
                    "IMPORTANTE: inclua o timestamp [MM:SS] no início de CADA turno de fala, "
                    "indicando o minuto e segundo em que aquela fala começa no áudio.\n"
                    "Se conseguir identificar quem fala, prefixe com 'COMISSÁRIO:' ou 'DECLARANTE:'.\n"
                    "Formato esperado de cada linha:\n"
                    "[01:23] COMISSÁRIO: Onde o senhor estava na noite do dia...\n"
                    "[01:45] DECLARANTE: Eu estava em casa com minha família...\n"
                    "Retorne apenas a transcrição com timestamps, sem comentários adicionais."
                ),
                part,
            ],
        )
        return {
            "transcricao": response.text.strip(),
            "tamanho_bytes": len(audio_bytes),
            "audio_url": audio_url,
        }
    except Exception as e:
        logger.error(f"[OITIVA] Erro na transcrição: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro na transcrição: {str(e)[:300]}")


@router.post("/lavrar")
async def lavrar_termo(body: LavrarRequest, db: AsyncSession = Depends(get_db)):
    """
    Converte transcrição em termo P&R formal com timestamps visuais.
    Cria registro em rascunho na tabela oitivas.
    Retorna termo_com_timestamps (exibição) + termo_limpo (copiar/colar).
    """
    from app.core.prompts import PROMPT_OITIVA
    from app.services.llm_service import LLMService
    from app.models.oitiva import OitivaGravada

    if len(body.transcricao) < 30:
        raise HTTPException(status_code=422, detail="Transcrição muito curta.")

    prompt = PROMPT_OITIVA.format(
        transcricao=body.transcricao,
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
        termo_com_ts = result["content"].strip()
        termo_limpo = _strip_timestamps(termo_com_ts)

        # Persiste como rascunho
        oitiva = OitivaGravada(
            id=uuid.uuid4(),
            inquerito_id=uuid.UUID(body.inquerito_id),
            pessoa_id=uuid.UUID(body.pessoa_id) if body.pessoa_id else None,
            audio_url=body.audio_url,
            transcricao_bruta=body.transcricao,
            termo_com_timestamps=termo_com_ts,
            termo_limpo=termo_limpo,
            duracao_segundos=body.duracao_segundos,
            status="rascunho",
        )
        db.add(oitiva)
        await db.commit()
        await db.refresh(oitiva)

        return {
            "oitiva_id": str(oitiva.id),
            "termo_com_timestamps": termo_com_ts,
            "termo_limpo": termo_limpo,
            "modelo": result.get("model"),
        }
    except Exception as e:
        logger.error(f"[OITIVA] Erro ao lavrar termo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar o termo: {str(e)[:300]}")


@router.post("/re-lavrar-bloco")
async def re_lavrar_bloco(body: RelavrarBlocoRequest):
    """
    Relava apenas um trecho/bloco da transcrição.
    Usado para corrigir uma declaração específica sem refazer o termo inteiro.
    """
    from app.core.prompts import PROMPT_OITIVA_RELAVRAR_BLOCO
    from app.services.llm_service import LLMService

    if len(body.trecho) < 10:
        raise HTTPException(status_code=422, detail="Trecho muito curto.")

    prompt = PROMPT_OITIVA_RELAVRAR_BLOCO.format(
        trecho=body.trecho,
        papel=body.papel,
    )
    llm = LLMService()
    try:
        result = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="premium",
            temperature=0.05,
            max_tokens=1000,
            agente="OitivaBloco",
        )
        bloco_com_ts = result["content"].strip()
        bloco_limpo = _strip_timestamps(bloco_com_ts)
        return {"bloco_com_timestamps": bloco_com_ts, "bloco_limpo": bloco_limpo}
    except Exception as e:
        logger.error(f"[OITIVA] Erro ao re-lavrar bloco: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao re-lavrar: {str(e)[:300]}")


@router.put("/{oitiva_id}")
async def atualizar_oitiva(
    oitiva_id: str,
    body: SalvarRequest,
    db: AsyncSession = Depends(get_db),
):
    """Atualiza termo editado e/ou status (rascunho→finalizado)."""
    from app.models.oitiva import OitivaGravada

    oitiva = await db.get(OitivaGravada, uuid.UUID(oitiva_id))
    if not oitiva:
        raise HTTPException(status_code=404, detail="Oitiva não encontrada.")

    oitiva.termo_com_timestamps = body.termo_com_timestamps
    oitiva.termo_limpo = _strip_timestamps(body.termo_com_timestamps)
    oitiva.status = body.status
    if body.pessoa_id:
        oitiva.pessoa_id = uuid.UUID(body.pessoa_id)
    oitiva.updated_at = datetime.utcnow()

    await db.commit()
    return {"ok": True, "status": oitiva.status}


@router.get("/inquerito/{inquerito_id}")
async def listar_oitivas(inquerito_id: str, db: AsyncSession = Depends(get_db)):
    """Lista todas as oitivas de um inquérito, ordenadas por data decrescente."""
    from app.models.oitiva import OitivaGravada
    from app.models.pessoa import Pessoa

    result = await db.execute(
        select(OitivaGravada)
        .where(OitivaGravada.inquerito_id == uuid.UUID(inquerito_id))
        .order_by(OitivaGravada.created_at.desc())
    )
    oitivas = result.scalars().all()

    items = []
    for o in oitivas:
        nome_pessoa = None
        if o.pessoa_id:
            p = await db.get(Pessoa, o.pessoa_id)
            nome_pessoa = p.nome if p else None
        items.append({
            "id": str(o.id),
            "pessoa_id": str(o.pessoa_id) if o.pessoa_id else None,
            "nome_pessoa": nome_pessoa,
            "audio_url": o.audio_url,
            "duracao_segundos": o.duracao_segundos,
            "status": o.status,
            "created_at": o.created_at.isoformat(),
            "preview": (o.termo_limpo or "")[:200],
        })
    return items


@router.get("/{oitiva_id}")
async def obter_oitiva(oitiva_id: str, db: AsyncSession = Depends(get_db)):
    """Retorna oitiva completa (termo com timestamps + limpo)."""
    from app.models.oitiva import OitivaGravada
    from app.models.pessoa import Pessoa

    oitiva = await db.get(OitivaGravada, uuid.UUID(oitiva_id))
    if not oitiva:
        raise HTTPException(status_code=404, detail="Oitiva não encontrada.")

    nome_pessoa = None
    if oitiva.pessoa_id:
        p = await db.get(Pessoa, oitiva.pessoa_id)
        nome_pessoa = p.nome if p else None

    return {
        "id": str(oitiva.id),
        "inquerito_id": str(oitiva.inquerito_id),
        "pessoa_id": str(oitiva.pessoa_id) if oitiva.pessoa_id else None,
        "nome_pessoa": nome_pessoa,
        "audio_url": oitiva.audio_url,
        "transcricao_bruta": oitiva.transcricao_bruta,
        "termo_com_timestamps": oitiva.termo_com_timestamps,
        "termo_limpo": oitiva.termo_limpo,
        "duracao_segundos": oitiva.duracao_segundos,
        "status": oitiva.status,
        "created_at": oitiva.created_at.isoformat(),
    }


@router.delete("/{oitiva_id}")
async def deletar_oitiva(oitiva_id: str, db: AsyncSession = Depends(get_db)):
    """Remove uma oitiva (apenas rascunhos)."""
    from app.models.oitiva import OitivaGravada

    oitiva = await db.get(OitivaGravada, uuid.UUID(oitiva_id))
    if not oitiva:
        raise HTTPException(status_code=404, detail="Oitiva não encontrada.")
    if oitiva.status == "finalizado":
        raise HTTPException(status_code=400, detail="Oitiva finalizada não pode ser removida.")

    await db.delete(oitiva)
    await db.commit()
    return {"ok": True}
