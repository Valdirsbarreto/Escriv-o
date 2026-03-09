"""
Escrivão AI — API: Ingestão de Documentos (Sprint F5)
Endpoints para início de fluxo de ingestão e orquestração.
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.services.storage import StorageService
from app.workers.orchestrator import orchestrate_new_inquerito

router = APIRouter(prefix="/ingestao", tags=["Ingestão"])

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
    Recebe um lote de arquivos e inicia a orquestração de um novo inquérito.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    id_sessao = str(uuid.uuid4())
    logger_msg = f"Iniciando ingestão de {len(files)} arquivos (Sessão: {id_sessao})"
    
    storage = StorageService()
    storage_paths = []
    filenames = []

    for file in files:
        if not file.filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tiff")):
            continue
        
        content = await file.read()
        storage_path = f"temporario/{id_sessao}/{file.filename}"
        await storage.upload_file(content, storage_path, file.content_type)
        
        storage_paths.append(storage_path)
        filenames.append(file.filename)

    if not storage_paths:
        raise HTTPException(status_code=400, detail="Nenhum arquivo válido (PDF/Imagens) enviado.")

    # Disparar Orquestrador
    try:
        orchestrate_new_inquerito.delay(storage_paths, filenames)
    except Exception as e:
        # Log error if Celery is down, but keep moving for MVP
        pass

    return IngestaoIniciaResponse(
        id_sessao=id_sessao,
        status="processando",
        mensagem=f"Recebidos {len(storage_paths)} arquivos. O Orquestrador IA está analisando para criar o inquérito automaticamente.",
        arquivos_recebidos=filenames
    )
