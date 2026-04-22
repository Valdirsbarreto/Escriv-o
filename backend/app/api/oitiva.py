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
    transcricao: Optional[str] = None
    papel: str = "testemunha"
    inquerito_id: str
    pessoa_id: Optional[str] = None
    audio_url: Optional[str] = None
    duracao_segundos: Optional[int] = None
    documento: Optional[str] = None  # documento pré-construído (pula LLM)


class LavrarSegmentoRequest(BaseModel):
    transcricao: str
    papel: str = "testemunha"
    segmento_idx: int = 0


class SherlockOitivaRequest(BaseModel):
    inquerito_id: str
    documento_atual: str


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


@router.post("/lavrar-segmento")
async def lavrar_segmento(body: LavrarSegmentoRequest):
    """
    Converte um segmento de transcrição em cláusulas "Que,".
    Não persiste no banco — só processa o texto.
    No primeiro segmento (idx==0) também extrai dados de qualificação em paralelo.
    """
    import asyncio
    import json as _json
    from app.core.prompts import PROMPT_OITIVA_SEGMENTO, PROMPT_EXTRAIR_QUALIFICACAO
    from app.services.llm_service import LLMService

    if len(body.transcricao.strip()) < 20:
        return {"texto": "", "qualificacao": None}

    llm = LLMService()

    prompt_texto = PROMPT_OITIVA_SEGMENTO.format(
        transcricao=body.transcricao,
        papel=body.papel,
        eh_primeiro_segmento="SIM" if body.segmento_idx == 0 else "NÃO",
    )

    coros = [
        llm.chat_completion(
            messages=[{"role": "user", "content": prompt_texto}],
            tier="premium",
            temperature=0.05,
            max_tokens=4000,
            agente="OitivaSegmento",
        )
    ]
    if body.segmento_idx == 0:
        coros.append(
            llm.chat_completion(
                messages=[{"role": "user", "content": PROMPT_EXTRAIR_QUALIFICACAO.format(
                    transcricao=body.transcricao[:3000],
                )}],
                tier="economico",
                temperature=0.0,
                max_tokens=500,
                agente="OitivaQualificacao",
            )
        )

    results = await asyncio.gather(*coros, return_exceptions=True)

    texto = ""
    if not isinstance(results[0], Exception):
        raw = results[0]["content"].strip()
        if raw != "[SEM_CONTEUDO]":
            texto = raw
    else:
        logger.warning(f"[OITIVA] Segmento {body.segmento_idx} lavrar falhou: {results[0]}")

    qualificacao = None
    if body.segmento_idx == 0 and len(results) > 1 and not isinstance(results[1], Exception):
        try:
            raw_q = results[1]["content"].strip()
            if "```" in raw_q:
                raw_q = raw_q.split("```")[1].lstrip("json").strip()
            qualificacao = _json.loads(raw_q)
        except Exception:
            pass

    return {"texto": texto, "qualificacao": qualificacao}


@router.post("/sherlock")
async def sherlock_oitiva(body: SherlockOitivaRequest, db: AsyncSession = Depends(get_db)):
    """
    Analisa a declaração em andamento versus o contexto do inquérito.
    Retorna consistência, inconsistências e perguntas sugeridas para o comissário.
    """
    import json as _json
    import uuid as _uuid
    from app.core.prompts import PROMPT_OITIVA_SHERLOCK
    from app.services.llm_service import LLMService
    from app.services.summary_service import SummaryService
    from app.models.documento_gerado import DocumentoGerado

    if len(body.documento_atual.strip()) < 30:
        raise HTTPException(status_code=422, detail="Declaração muito curta para análise.")

    # Monta contexto do inquérito (relatório inicial + resumo)
    contexto_parts = []
    try:
        inq_id = _uuid.UUID(body.inquerito_id)
        # Relatório inicial
        result = await db.execute(
            select(DocumentoGerado)
            .where(
                DocumentoGerado.inquerito_id == inq_id,
                DocumentoGerado.tipo == "relatorio_inicial",
                DocumentoGerado.conteudo != "__PROCESSANDO__",
            )
            .order_by(DocumentoGerado.created_at.desc())
            .limit(1)
        )
        rel = result.scalar_one_or_none()
        if rel and rel.conteudo:
            contexto_parts.append("=== RELATÓRIO INICIAL ===\n" + rel.conteudo[:8000])

        # Resumo do caso
        summary_svc = SummaryService(db)
        resumo = await summary_svc.obter_resumo_caso(inq_id)
        if resumo:
            contexto_parts.append("=== RESUMO EXECUTIVO ===\n" + resumo[:3000])
    except Exception as e:
        logger.warning(f"[OITIVA-SHERLOCK] Contexto parcial: {e}")

    contexto = "\n\n".join(contexto_parts) if contexto_parts else "Contexto do inquérito não disponível."

    prompt = PROMPT_OITIVA_SHERLOCK.format(
        contexto_inquerito=contexto,
        documento_atual=body.documento_atual[:6000],
    )

    llm = LLMService()
    try:
        result = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="premium",
            temperature=0.1,
            max_tokens=2000,
            agente="SherlockOitiva",
        )
        raw = result["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return _json.loads(raw)
    except Exception as e:
        logger.error(f"[OITIVA-SHERLOCK] Erro: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro na análise: {str(e)[:200]}")


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

    if not body.documento and (not body.transcricao or len(body.transcricao) < 30):
        raise HTTPException(status_code=422, detail="Transcrição muito curta.")

    llm = LLMService()
    try:
        if body.documento:
            # Documento pré-construído via segmentos progressivos — usar diretamente
            termo_com_ts = body.documento
            termo_limpo = body.documento
        else:
            # Caminho legado: gera via LLM a partir da transcrição bruta
            prompt = PROMPT_OITIVA.format(
                transcricao=body.transcricao,
                papel=body.papel,
            )
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
            transcricao_bruta=body.transcricao or "",
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
