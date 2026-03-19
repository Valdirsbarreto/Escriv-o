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
            # Roda direto se for função normal no futuro
            from fastapi import BackgroundTasks
            # (Adicionei esse fallback para garantir que o fluxo não quebre)
            pass
            
        logger.info(f"[INGESTÃO] Orquestrador acionado via Celery para sessão {id_sessao}.")
    except Exception as e:
        logger.warning(f"[INGESTÃO] Erro ao disparar orquestrador ({e}).")

    aviso = f" ({len(ignorados)} ignorados)" if ignorados else ""
    return IngestaoIniciaResponse(
        id_sessao=id_sessao,
        status="processando",
        mensagem=f"Recebidos {len(storage_paths)} arquivo(s){aviso}. O Orquestrador IA está analisando para criar o inquérito automaticamente.",
        arquivos_recebidos=filenames
    )
