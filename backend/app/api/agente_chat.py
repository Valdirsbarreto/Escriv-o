"""
Escrivão AI — API: Chat do Agente Web
Endpoint para o widget de chat web usando CopilotoService (RAG completo).
Substituiu TelegramCopilotoService que requeria Gemini Function Calling (403 no projeto).
"""

import io
import json
import logging
import re
import struct
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
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
    texto_anexo: Optional[str] = None   # texto/descrição de arquivo já processado
    nome_anexo: Optional[str] = None    # nome original do arquivo


class ChatResponse(BaseModel):
    resposta: str
    inquerito_id: Optional[str] = None  # IP resolvido (para atualizar store no frontend)


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
            # Tenta busca global por nome/apelido/CPF em todos os inquéritos
            resultados_global = await _buscar_global(body.mensagem, db)
            if resultados_global:
                # Se resultado único — carrega o inquérito automaticamente e segue
                if len(resultados_global) == 1 and resultados_global[0]["inquerito_id"]:
                    await _sync_inquerito_context(
                        body.session_id, resultados_global[0]["inquerito_id"], db, ctx
                    )
                    inquerito_id = resultados_global[0]["inquerito_id"]
                    logger.info(f"[AGENT-CHAT] IP resolvido por busca global: {resultados_global[0]['numero']}")
                else:
                    # Múltiplos IPs — injeta resultados como contexto e deixa o LLM responder
                    import json as _json
                    ctx_global = _json.dumps(resultados_global, ensure_ascii=False, indent=2)
                    try:
                        res_lm = await _get_copiloto().processar_mensagem_global(
                            query=body.mensagem,
                            db=db,
                            historico=ctx.get("historico", []),
                            resultados_precomputados=resultados_global,
                        )
                        resposta_global = res_lm.get("resposta", "")
                    except Exception as e:
                        logger.warning(f"[AGENT-CHAT] processar_mensagem_global falhou: {e}")
                        linhas = [
                            f"• **{r['numero']}**" +
                            (f" — {r['descricao'][:60]}" if r.get('descricao') else "") +
                            (f"\n  {', '.join(r['mencoes'][:2])}" if r.get('mencoes') else "")
                            for r in resultados_global[:8]
                        ]
                        resposta_global = f"Encontrei menções em {len(resultados_global)} inquérito(s):\n\n" + "\n".join(linhas) + "\n\nQual deseja abrir, Comissário?"

                    # Atualiza histórico
                    hist = ctx.get("historico", [])
                    hist.append({"role": "user", "content": body.mensagem[:1000]})
                    hist.append({"role": "model", "content": resposta_global[:2000]})
                    if len(hist) > 30:
                        hist = hist[-30:]
                    ctx["historico"] = hist
                    await _save_ctx(body.session_id, ctx)
                    return ChatResponse(resposta=resposta_global, inquerito_id=None)
            if not inquerito_id:
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
            auditar=False,
            db=db,
            texto_anexo=body.texto_anexo,
            nome_anexo=body.nome_anexo,
        )
    except Exception as e:
        logger.error(f"[AGENT-CHAT] Erro ao processar mensagem: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao processar mensagem")

    resposta = resultado.get("resposta", "Não consegui processar. Tente novamente.")

    # Atualizar histórico (limites maiores para manter contexto conversacional)
    historico = ctx.get("historico", [])
    historico.append({"role": "user", "content": body.mensagem[:1000]})
    historico.append({"role": "model", "content": resposta[:2000]})
    if len(historico) > 30:
        historico = historico[-30:]
    ctx["historico"] = historico
    await _save_ctx(body.session_id, ctx)

    return ChatResponse(resposta=resposta, inquerito_id=inquerito_id)


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


from fastapi import UploadFile, File


@router.post("/analisar-documento", summary="Vision — analisa imagem/PDF e detecta mandados de intimação")
async def analisar_documento(
    arquivo: UploadFile = File(...),
    x_chat_secret: str = Header(default=""),
):
    """
    Recebe imagem (JPEG/PNG/WEBP) ou PDF e retorna análise via Gemini.
    Se for mandado de intimação/oitiva com data e hora, extrai dados para agenda.
    Funciona com qualquer formato de documento policial.
    """
    _check_auth(x_chat_secret)

    conteudo = await arquivo.read()
    if len(conteudo) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 20MB)")

    mime = arquivo.content_type or "application/octet-stream"
    nome = arquivo.filename or "documento"

    # Normaliza mime types comuns
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext == "pdf" or "pdf" in mime:
        mime = "application/pdf"
    elif ext in ("jpg", "jpeg") or "jpeg" in mime:
        mime = "image/jpeg"
    elif ext == "png" or "png" in mime:
        mime = "image/png"
    elif ext == "webp" or "webp" in mime:
        mime = "image/webp"

    # Gemini suporta imagens e PDFs inline
    suportado = mime in ("image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf")
    if not suportado:
        return {"descricao": f"Arquivo {nome} recebido (formato {ext} não suportado para análise automática).", "tipo": "outro", "dados_intimacao": None, "nome": nome}

    try:
        from google import genai as _genai
        from google.genai import types as _genai_types

        client = _genai.Client(api_key=settings.GEMINI_API_KEY)
        part = _genai_types.Part.from_bytes(data=conteudo, mime_type=mime)

        prompt = (
            "Analise este documento cuidadosamente. Responda SOMENTE em JSON com este formato:\n"
            "{\n"
            '  "descricao": "transcrição ou descrição detalhada do conteúdo",\n'
            '  "tipo": "intimacao" ou "outro",\n'
            '  "dados_intimacao": null ou {\n'
            '    "intimado_nome": "nome completo do intimado/convocado",\n'
            '    "data_oitiva": "YYYY-MM-DDTHH:MM:00",\n'
            '    "local_oitiva": "endereço/local completo" ou null,\n'
            '    "numero_inquerito": "número do IP/inquérito" ou null,\n'
            '    "qualificacao": "cargo/qualificação" ou null\n'
            "  }\n"
            "}\n\n"
            "REGRAS:\n"
            "- tipo='intimacao' se o documento for mandado de intimação, convocação para oitiva/depoimento, "
            "citação judicial ou policial COM data e hora marcadas para comparecer\n"
            "- Se for intimação mas SEM data/hora definida: tipo='intimacao', data_oitiva=null\n"
            "- Para qualquer outro documento (laudo, boletim, foto, etc.): tipo='outro'\n"
            "- Para data_oitiva: formato ISO 8601. Se só tiver a data sem hora, use T09:00:00\n"
            "- Se o PDF tiver múltiplas páginas, analise todas e extraia o que for mais relevante\n"
            "- Retorne SOMENTE o JSON, sem markdown, sem explicações"
        )

        response = await client.aio.models.generate_content(
            model=settings.LLM_STANDARD_MODEL,
            contents=[prompt, part],
        )

        raw = response.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw).rstrip("`").strip()

        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"descricao": raw, "tipo": "outro", "dados_intimacao": None}

        return {
            "descricao": parsed.get("descricao", raw),
            "tipo": parsed.get("tipo", "outro"),
            "dados_intimacao": parsed.get("dados_intimacao"),
            "nome": nome,
        }
    except Exception as e:
        logger.error(f"[VISION] Erro ao analisar documento: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao analisar documento")


class TtsRequest(BaseModel):
    texto: str


@router.post("/tts", summary="TTS — converte texto em áudio Gemini (voz natural)")
async def agent_tts(
    body: TtsRequest,
    x_chat_secret: str = Header(default=""),
):
    """
    Converte uma resposta de texto em áudio WAV usando Gemini TTS.
    Mesma voz usada no Telegram. Retorna audio/wav.
    """
    _check_auth(x_chat_secret)
    if not body.texto.strip():
        raise HTTPException(status_code=422, detail="Texto vazio")

    texto_voz = await _resumir_para_voz(body.texto)
    wav_bytes = await _gerar_audio_tts(texto_voz)
    if not wav_bytes:
        raise HTTPException(status_code=503, detail="TTS indisponível")

    return Response(content=wav_bytes, media_type="audio/wav")


# ── TTS helpers ────────────────────────────────────────────────────────────────


def _pcm_para_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    n_canais, sample_width = 1, 2
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(pcm_data)))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))
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
    texto_limpo = re.sub(r"<[^>]+>", " ", texto_html)
    texto_limpo = re.sub(r"&\w+;", " ", texto_limpo)
    texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()

    if len(texto_limpo) <= 200:
        return texto_limpo

    try:
        from google import genai as _genai
        client = _genai.Client(api_key=settings.GEMINI_API_KEY)
        response = await client.aio.models.generate_content(
            model=settings.LLM_ECONOMICO_MODEL,
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
        logger.warning(f"[TTS-WEB] Resumo falhou: {e}")
        match = re.search(r"[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][^.!?]{15,180}[.!?]", texto_limpo)
        return match.group(0) if match else texto_limpo[:250]


async def _gerar_audio_tts(texto_para_falar: str) -> Optional[bytes]:
    try:
        from google import genai as _genai
        from google.genai import types as _genai_types
        import base64

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
            pcm_data = base64.b64decode(pcm_data)
        return _pcm_para_wav(pcm_data)
    except Exception as e:
        logger.warning(f"[TTS-WEB] Geração falhou: {e}")
        return None


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


async def _buscar_global(mensagem: str, db: AsyncSession) -> list:
    """
    Busca nome, apelido ou CPF em TODOS os inquéritos.
    Retorna lista de dicts {inquerito_id, numero, descricao, mencoes[]}.
    Usado quando o Comissário pergunta sobre alguém sem saber o número do IP.
    """
    import unicodedata
    from sqlalchemy import func as sa_func, or_
    from app.models.pessoa import Pessoa
    from app.models.chunk import Chunk

    # Extrair termos de busca: nomes próprios (caps) e possível CPF
    termos = []

    # CPF: sequência de 11 dígitos ou formatado
    cpf_match = re.findall(r'\d{3}[\.\-]?\d{3}[\.\-]?\d{3}[\-\.]?\d{2}', mensagem)
    for c in cpf_match:
        termos.append(re.sub(r'[\.\-]', '', c))

    # Nomes próprios: palavras capitalizadas com ≥ 3 chars que não sejam stopwords comuns
    _SW = {'que', 'tem', 'tem', 'sobre', 'para', 'como', 'qual', 'quem',
           'tem', 'algum', 'alguma', 'sabe', 'saber', 'existe', 'existir',
           'ver', 'veja', 'voce', 'você', 'sim', 'não', 'nao', 'este', 'esse',
           'esse', 'isso', 'aqui', 'ali', 'lembro', 'acho', 'inquerito', 'policial',
           'nacional', 'conhecido', 'apelido', 'alcunha', 'nome', 'pessoa'}

    def strip_acc(s):
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

    tokens = mensagem.split()
    for i, tok in enumerate(tokens):
        palavra = re.sub(r'[^\w]', '', tok)
        if len(palavra) < 3:
            continue
        if strip_acc(palavra.lower()) in _SW:
            continue
        # Aceita palavras capitalizadas (nomes) OU qualquer palavra entre aspas/parênteses
        if palavra[0].isupper() and i > 0:
            termos.append(palavra)
        # Palavras entre aspas na mensagem original
        quoted = re.findall(r'["\']([^"\']{3,})["\']', mensagem)
        termos.extend(quoted)

    # Remove duplicatas e normaliza
    termos_norm = list({strip_acc(t.lower()) for t in termos if len(t) >= 3})
    if not termos_norm:
        return []

    logger.info(f"[BUSCA-GLOBAL] Termos: {termos_norm}")

    # ── 1. Busca na tabela Pessoa (nome, observações, CPF) ────────────────────
    filtros_pessoa = [
        sa_func.unaccent(sa_func.lower(Pessoa.nome)).ilike(f"%{t}%")
        for t in termos_norm[:4]
    ] + [
        sa_func.unaccent(sa_func.lower(Pessoa.observacoes)).ilike(f"%{t}%")
        for t in termos_norm[:2] if Pessoa.observacoes is not None
    ] + [Pessoa.cpf.ilike(f"%{t}%") for t in termos_norm if t.isdigit()]

    try:
        res_pessoas = await db.execute(
            select(Pessoa.inquerito_id, Pessoa.nome, Pessoa.tipo_pessoa)
            .where(or_(*filtros_pessoa))
            .limit(20)
        )
        rows_pessoas = res_pessoas.all()
    except Exception:
        rows_pessoas = []

    # ── 2. Busca em chunks (apelidos / menções não cadastradas) ───────────────
    filtros_chunk = [
        sa_func.unaccent(sa_func.lower(Chunk.texto)).ilike(f"%{t}%")
        for t in termos_norm[:3]
    ]
    try:
        from sqlalchemy import and_ as sa_and
        combinar = sa_and if len(filtros_chunk) <= 2 else or_
        res_chunks = await db.execute(
            select(Chunk.inquerito_id, Chunk.texto)
            .where(combinar(*filtros_chunk))
            .limit(30)
        )
        rows_chunks = res_chunks.all()
    except Exception:
        rows_chunks = []

    # ── Agrupar por inquérito ─────────────────────────────────────────────────
    por_inquerito: dict = {}
    for row in rows_pessoas:
        iid = str(row.inquerito_id)
        por_inquerito.setdefault(iid, {"mencoes": set()})
        por_inquerito[iid]["mencoes"].add(f"{row.nome} [{row.tipo_pessoa or 'pessoa'}]")

    for row in rows_chunks:
        iid = str(row.inquerito_id)
        por_inquerito.setdefault(iid, {"mencoes": set()})
        # Extrai trecho do contexto ao redor do termo
        texto = row.texto
        for t in termos_norm:
            idx = strip_acc(texto.lower()).find(t)
            if idx >= 0:
                inicio = max(0, idx - 40)
                fim = min(len(texto), idx + len(t) + 60)
                por_inquerito[iid]["mencoes"].add(f"...{texto[inicio:fim].strip()}...")
                break

    if not por_inquerito:
        return []

    # Enriquecer com dados do inquérito
    ids = [uuid.UUID(i) for i in por_inquerito.keys()]
    res_inq = await db.execute(
        select(Inquerito.id, Inquerito.numero, Inquerito.descricao)
        .where(Inquerito.id.in_(ids))
        .order_by(Inquerito.updated_at.desc())
    )
    resultado = []
    for inq in res_inq.all():
        iid = str(inq.id)
        resultado.append({
            "inquerito_id": iid,
            "numero": inq.numero,
            "descricao": inq.descricao or "",
            "mencoes": list(por_inquerito[iid]["mencoes"])[:3],
        })

    logger.info(f"[BUSCA-GLOBAL] {len(resultado)} inquérito(s) encontrado(s)")
    return resultado


async def _sync_inquerito_context(
    session_id: str, inquerito_id: str, db: AsyncSession, ctx: dict
) -> str:
    from sqlalchemy import func as sa_func
    from app.models.documento import Documento

    result = await db.execute(select(Inquerito).where(Inquerito.id == inquerito_id))
    ip = result.scalars().first()
    if not ip:
        return ""

    # Conta documentos reais indexados — o campo ip.total_documentos pode estar desatualizado
    # e se for 0, o system prompt diz "0 documentos indexados", confundindo o LLM
    try:
        cnt = await db.execute(
            select(sa_func.count(Documento.id), sa_func.sum(Documento.total_paginas))
            .where(Documento.inquerito_id == ip.id)
            .where(Documento.status_processamento == "concluido")
        )
        total_docs, total_pgs = cnt.one()
        total_docs = total_docs or 0
        total_pgs = int(total_pgs or 0)
    except Exception:
        total_docs = ip.total_documentos or 0
        total_pgs = ip.total_paginas or 0

    ctx["inquerito_id"] = str(ip.id)
    ctx["inquerito_numero"] = ip.numero
    ctx["estado_atual"] = ip.estado_atual or ""
    ctx["total_documentos"] = total_docs
    ctx["total_paginas"] = total_pgs
    await _save_ctx(session_id, ctx)
    return ip.numero
