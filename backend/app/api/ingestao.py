"""
Escrivão AI — API: Ingestão de Documentos (Sprint F5)
Endpoints para início de fluxo de ingestão e orquestração.
"""

import uuid
import logging
from typing import List
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.services.storage import StorageService
from app.workers.orchestrator import orchestrate_new_inquerito

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingestao", tags=["Ingestão"])

EXTENSOES_PERMITIDAS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
TAMANHO_MAX_ARQUIVO = 50 * 1024 * 1024  # 50 MB por arquivo


class IngestaoIniciaResponse(BaseModel):
    id_sessao: str
    status: str
    mensagem: str
    arquivos_recebidos: List[str]


@router.post("/iniciar", response_model=IngestaoIniciaResponse)
async def iniciar_ingestao(
    files: List[UploadFile] = File(...),
):
    """
    Recebe um lote de arquivos (max 50 MB / arquivo) e inicia a orquestração.
    O frontend envia em batches de 10; cada chamada é independente.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    id_sessao = str(uuid.uuid4())
    logger.info(f"[INGESTÃO] Sessão {id_sessao} — recebendo {len(files)} arquivo(s).")

    storage = StorageService()
    storage_paths = []
    filenames = []
    ignorados = []

    import re
    import unicodedata

    def slugify(text: str) -> str:
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        text = re.sub(r'[^\w\s\.-]', '', text).strip().lower()
        return re.sub(r'[-\s]+', '-', text)

    for file in files:
        nome_original = file.filename or "arquivo"
        nome = slugify(nome_original)
        ext = "." + nome_original.rsplit(".", 1)[-1].lower() if "." in nome_original else ""
        if not nome.endswith(ext):
            nome += ext
        
        if ext not in EXTENSOES_PERMITIDAS:
            ignorados.append(nome_original)
            continue

        try:
            content = await file.read()
            if len(content) > TAMANHO_MAX_ARQUIVO:
                logger.warning(f"[INGESTÃO] Arquivo {nome_original} excede 50 MB, ignorado.")
                ignorados.append(nome_original)
                continue

            storage_path = f"temporario/{id_sessao}/{nome}"
            await storage.upload_file(content, storage_path, file.content_type or "application/octet-stream")
            storage_paths.append(storage_path)
            filenames.append(nome_original)
        except Exception as e:
            logger.error(f"[INGESTÃO] Erro ao processar {nome_original}: {e}")
            ignorados.append(nome_original)

    if not storage_paths:
        raise HTTPException(
            status_code=400,
            detail=f"Nenhum arquivo válido encontrado. Ignorados: {ignorados}"
        )

    # Disparar Orquestrador em background (Nativo FastAPI)
    try:
        if hasattr(orchestrate_new_inquerito, "delay"):
            # Tenta Celery primeiro (se estiver ativo)
            orchestrate_new_inquerito.delay(storage_paths, filenames)
        else:
            # Fallback para processamento imediato (não recomendado em prod)
            logger.warning("[INGESTÃO] Celery indisponível. Orquestração não iniciada.")
            raise HTTPException(status_code=503, detail="Serviço de processamento (Celery/Redis) indisponível.")
            
        logger.info(f"[INGESTÃO] Orquestrador acionado via Celery para sessão {id_sessao}.")
    except Exception as e:
        logger.error(f"[INGESTÃO] Falha ao disparar orquestrador ({e}).")
        raise HTTPException(
            status_code=500,
            detail=f"Não foi possível iniciar o processamento dos documentos: {str(e)}"
        )

    aviso = f" ({len(ignorados)} ignorados)" if ignorados else ""
    return IngestaoIniciaResponse(
        id_sessao=id_sessao,
        status="processando",
        mensagem=f"Recebidos {len(storage_paths)} arquivo(s){aviso}. O Orquestrador IA está analisando para criar o inquérito automaticamente.",
        arquivos_recebidos=filenames
    )


# ── Admin: Gerenciamento Qdrant ───────────────────────────────────────────────

@router.post("/admin/qdrant/recreate", tags=["Admin"])
async def admin_recreate_qdrant():
    """
    Apaga e recria a coleção Qdrant com as dimensões corretas (768-dim / text-embedding-004).
    ATENÇÃO: apaga todos os vetores indexados — re-indexar documentos após executar.
    """
    from app.services.qdrant_service import QdrantService
    svc = QdrantService()
    result = svc.recreate_collection()
    return result


@router.get("/admin/qdrant/info", tags=["Admin"])
async def admin_qdrant_info():
    """Retorna informações da coleção Qdrant (dims, total de pontos, status)."""
    from app.services.qdrant_service import QdrantService
    svc = QdrantService()
    try:
        info = svc.client.get_collection(svc.collection_name)
        config = info.config.params.vectors
        dims = config.size if hasattr(config, "size") else "?"
        return {
            "collection": svc.collection_name,
            "dims": dims,
            "points_count": info.points_count,
            "status": info.status.value,
        }
    except Exception as e:
        return {"erro": str(e)}


@router.post("/admin/reindexa/{inquerito_id}", tags=["Admin"])
async def admin_reindexa_inquerito(inquerito_id: uuid.UUID):
    """
    Re-dispara a ingestão de todos os documentos de um inquérito já existente.
    Útil para re-indexar no Qdrant após recriar a coleção com dimensões corretas.
    Os chunks antigos no PostgreSQL são apagados antes de reprocessar para evitar duplicatas.
    """
    from sqlalchemy import create_engine, select as sa_select, delete as sa_delete
    from sqlalchemy.orm import Session
    from app.core.config import settings as _s
    from app.models.documento import Documento
    from app.models.chunk import Chunk
    from app.workers.ingestion import ingest_document

    sync_engine = create_engine(_s.DATABASE_URL_SYNC)
    disparados = []
    ignorados = []

    with Session(sync_engine) as db:
        docs = db.execute(
            sa_select(Documento)
            .where(Documento.inquerito_id == inquerito_id)
            .where(Documento.status_processamento == "concluido")
        ).scalars().all()

        if not docs:
            return {"ok": False, "mensagem": "Nenhum documento concluído encontrado para este inquérito."}

        for doc in docs:
            # Apaga chunks antigos do PostgreSQL para evitar duplicatas
            db.execute(
                sa_delete(Chunk).where(Chunk.documento_id == doc.id)
            )
            # Marca para reprocessamento
            doc.status_processamento = "pendente"

        db.commit()

        # Dispara re-ingestão para cada documento
        for doc in docs:
            ingest_document.delay(str(doc.id), str(inquerito_id))
            disparados.append(str(doc.id))

    return {
        "ok": True,
        "inquerito_id": str(inquerito_id),
        "documentos_disparados": len(disparados),
        "ids": disparados,
    }
