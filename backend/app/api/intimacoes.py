"""
Escrivão AI — API: Intimações
Upload de intimações, listagem, correção de dados e sincronização com Google Agenda.
"""

import hashlib
import logging
import re
import unicodedata
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.models.intimacao import Intimacao
from app.models.documento import Documento
from app.models.inquerito import Inquerito
from app.schemas.intimacao import IntimacaoResponse, IntimacaoUpdate, IntimacaoUploadResponse, IntimacaoManualCreate
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intimacoes", tags=["Intimações"])


def _sanitize_storage_key(filename: str) -> str:
    """Remove acentos e caracteres especiais para uso como chave S3."""
    name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^\w.\-]", "_", name)


# ── Upload ───────────────────────────────────────────────────────


@router.post("/upload", response_model=IntimacaoUploadResponse, status_code=201)
async def upload_intimacao(
    file: UploadFile = File(...),
    inquerito_id: Optional[uuid.UUID] = Query(
        None, description="Vínculo manual com inquérito (opcional, o sistema tenta detectar automaticamente)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe um PDF ou foto de intimação, salva no storage e dispara o
    processamento assíncrono (OCR → extração LLM → Google Agenda).
    """
    if not file.filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tiff")):
        raise HTTPException(
            status_code=400,
            detail="Formato não suportado. Use PDF, PNG, JPG ou TIFF.",
        )

    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    # Verifica se o inquérito existe quando informado manualmente
    if inquerito_id:
        inq = await db.get(Inquerito, inquerito_id)
        if not inq:
            raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    # Salva arquivo no storage (chave S3 sem acentos; nome exibido preserva o original)
    storage = StorageService()
    pasta = f"inqueritos/{inquerito_id}" if inquerito_id else "intimacoes/avulsas"
    safe_filename = _sanitize_storage_key(file.filename)
    storage_path = f"{pasta}/{safe_filename}"
    await storage.upload_file(content, storage_path, file.content_type)

    # Só cria Documento se houver inquérito (documentos.inquerito_id não pode ser null
    # em registros de autos — para intimações avulsas, guardamos o path direto na intimação)
    documento_id = None
    if inquerito_id:
        documento = Documento(
            inquerito_id=inquerito_id,
            nome_arquivo=file.filename,
            hash_arquivo=file_hash,
            storage_path=storage_path,
            status_processamento="pendente",
        )
        db.add(documento)
        await db.flush()
        await db.refresh(documento)
        documento_id = documento.id

    # Cria registro da intimação (será preenchido pela task)
    intimacao = Intimacao(
        inquerito_id=inquerito_id,
        documento_id=documento_id,
        storage_path=storage_path,
        status="agendada",
    )
    db.add(intimacao)
    await db.flush()
    await db.refresh(intimacao)

    # Dispara task assíncrona
    task_id = None
    try:
        from app.workers.intimacao_task import processar_intimacao
        result = processar_intimacao.delay(str(intimacao.id))
        task_id = result.id
    except Exception as e:
        logger.error(f"[INTIMACAO] Falha ao disparar task: {e}")

    await db.commit()

    return IntimacaoUploadResponse(
        intimacao_id=intimacao.id,
        nome_arquivo=file.filename,
        status="processando",
        mensagem="Intimação recebida. Extração de dados em andamento.",
        task_id=task_id,
    )


# ── Lançamento Manual ────────────────────────────────────────────


@router.post("/manual", response_model=IntimacaoResponse, status_code=201)
async def criar_intimacao_manual(
    dados: IntimacaoManualCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria uma intimação manualmente (sem upload de arquivo) e já
    agenda o evento no Google Agenda na hora.
    """
    # Verifica inquérito se informado
    if dados.inquerito_id:
        inq = await db.get(Inquerito, dados.inquerito_id)
        if not inq:
            raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    # Se não veio inquerito_id mas veio numero, tenta encontrar
    inquerito_id = dados.inquerito_id
    if not inquerito_id and dados.numero_inquerito_extraido:
        result = await db.execute(
            select(Inquerito).where(Inquerito.numero == dados.numero_inquerito_extraido)
        )
        inq = result.scalar_one_or_none()
        if inq:
            inquerito_id = inq.id

    intimacao = Intimacao(
        inquerito_id=inquerito_id,
        intimado_nome=dados.intimado_nome,
        intimado_qualificacao=dados.intimado_qualificacao,
        numero_inquerito_extraido=dados.numero_inquerito_extraido,
        data_oitiva=dados.data_oitiva,
        local_oitiva=dados.local_oitiva,
        status="agendada",
    )
    db.add(intimacao)
    await db.flush()

    # Cria evento no Google Agenda imediatamente (sem worker)
    try:
        from app.services.google_calendar_service import GoogleCalendarService
        gcal = GoogleCalendarService()
        evento = gcal.criar_evento_oitiva(
            intimado_nome=dados.intimado_nome,
            data_oitiva=dados.data_oitiva,
            numero_inquerito=dados.numero_inquerito_extraido,
            local_oitiva=dados.local_oitiva,
            qualificacao=dados.intimado_qualificacao,
        )
        intimacao.google_event_id = evento.get("event_id")
        intimacao.google_event_url = evento.get("event_url")
    except RuntimeError as e:
        logger.warning(f"[INTIMACAO-MANUAL] Google Calendar não configurado: {e}")
    except Exception as e:
        logger.error(f"[INTIMACAO-MANUAL] Erro ao criar evento Google: {e}")

    await db.commit()
    await db.refresh(intimacao)
    return intimacao


# ── Listagem ─────────────────────────────────────────────────────


@router.get("", response_model=list[IntimacaoResponse])
async def listar_intimacoes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    db: AsyncSession = Depends(get_db),
):
    """Lista todas as intimações, ordenadas pela data da oitiva."""
    query = select(Intimacao)
    if status:
        query = query.where(Intimacao.status == status)
    query = query.order_by(Intimacao.data_oitiva.asc().nullslast()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/inquerito/{inquerito_id}", response_model=list[IntimacaoResponse])
async def listar_intimacoes_inquerito(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Lista as intimações vinculadas a um inquérito específico."""
    result = await db.execute(
        select(Intimacao)
        .where(Intimacao.inquerito_id == inquerito_id)
        .order_by(Intimacao.data_oitiva.asc().nullslast())
    )
    return result.scalars().all()


@router.get("/{intimacao_id}", response_model=IntimacaoResponse)
async def obter_intimacao(
    intimacao_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    intimacao = await db.get(Intimacao, intimacao_id)
    if not intimacao:
        raise HTTPException(status_code=404, detail="Intimação não encontrada")
    return intimacao


# ── Correção de dados ─────────────────────────────────────────────


@router.patch("/{intimacao_id}", response_model=IntimacaoResponse)
async def atualizar_intimacao(
    intimacao_id: uuid.UUID,
    dados: IntimacaoUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Corrige dados extraídos e re-sincroniza o evento no Google Agenda se necessário.
    """
    intimacao = await db.get(Intimacao, intimacao_id)
    if not intimacao:
        raise HTTPException(status_code=404, detail="Intimação não encontrada")

    update_data = dados.model_dump(exclude_unset=True)
    recria_evento = False

    for field, value in update_data.items():
        if field in ("data_oitiva", "local_oitiva", "intimado_nome", "intimado_qualificacao"):
            if getattr(intimacao, field) != value:
                recria_evento = True
        setattr(intimacao, field, value)

    # Se mudou campos relevantes e já tem evento, atualiza no Google
    if recria_evento and intimacao.google_event_id and intimacao.data_oitiva and intimacao.intimado_nome:
        try:
            from app.services.google_calendar_service import GoogleCalendarService
            gcal = GoogleCalendarService()
            evento = gcal.atualizar_evento_oitiva(
                event_id=intimacao.google_event_id,
                intimado_nome=intimacao.intimado_nome,
                data_oitiva=intimacao.data_oitiva,
                numero_inquerito=intimacao.numero_inquerito_extraido,
                local_oitiva=intimacao.local_oitiva,
                qualificacao=intimacao.intimado_qualificacao,
            )
            intimacao.google_event_url = evento.get("event_url")
        except Exception as e:
            logger.warning(f"[INTIMACAO] Não foi possível atualizar evento Google: {e}")

    # Se não tinha evento mas agora tem data e nome, tenta criar
    elif recria_evento and not intimacao.google_event_id and intimacao.data_oitiva and intimacao.intimado_nome:
        try:
            from app.services.google_calendar_service import GoogleCalendarService
            gcal = GoogleCalendarService()
            evento = gcal.criar_evento_oitiva(
                intimado_nome=intimacao.intimado_nome,
                data_oitiva=intimacao.data_oitiva,
                numero_inquerito=intimacao.numero_inquerito_extraido,
                local_oitiva=intimacao.local_oitiva,
                qualificacao=intimacao.intimado_qualificacao,
            )
            intimacao.google_event_id = evento.get("event_id")
            intimacao.google_event_url = evento.get("event_url")
        except Exception as e:
            logger.warning(f"[INTIMACAO] Não foi possível criar evento Google: {e}")

    await db.commit()
    await db.refresh(intimacao)
    return intimacao


# ── Cancelamento ─────────────────────────────────────────────────


@router.delete("/{intimacao_id}", status_code=204)
async def cancelar_intimacao(
    intimacao_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Cancela a intimação e remove o evento do Google Agenda."""
    intimacao = await db.get(Intimacao, intimacao_id)
    if not intimacao:
        raise HTTPException(status_code=404, detail="Intimação não encontrada")

    if intimacao.google_event_id:
        try:
            from app.services.google_calendar_service import GoogleCalendarService
            GoogleCalendarService().cancelar_evento(intimacao.google_event_id)
        except Exception as e:
            logger.warning(f"[INTIMACAO] Não foi possível remover evento Google: {e}")

    await db.delete(intimacao)
    await db.commit()
