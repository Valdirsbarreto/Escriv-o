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


@router.post("/iniciar-url", response_model=IngestaoIniciaResponse)
async def iniciar_ingestao_por_url(body: dict):
    """
    Baixa um arquivo de uma URL remota (ex: OneDrive) e inicia a orquestração.
    Body: { "url": "https://...", "nome_arquivo": "doc.pdf" }
    """
    import re, unicodedata, httpx

    url = (body.get("url") or "").strip()
    nome_original = (body.get("nome_arquivo") or "documento.pdf").strip()

    if not url:
        raise HTTPException(status_code=400, detail="URL não informada.")

    ext = "." + nome_original.rsplit(".", 1)[-1].lower() if "." in nome_original else ""
    if ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=400, detail=f"Formato {ext} não suportado.")

    # Baixar da URL remota
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                raise HTTPException(status_code=422, detail=f"Erro ao baixar arquivo (HTTP {resp.status_code})")
            content = resp.content
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro ao baixar arquivo: {str(e)[:200]}")

    if len(content) < 100:
        raise HTTPException(status_code=422, detail="Arquivo baixado está vazio ou inválido.")
    if len(content) > TAMANHO_MAX_ARQUIVO:
        raise HTTPException(status_code=400, detail="Arquivo excede 50 MB.")

    def slugify(text: str) -> str:
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        text = re.sub(r'[^\w\s\.-]', '', text).strip().lower()
        return re.sub(r'[-\s]+', '-', text)

    nome = slugify(nome_original)
    if not nome.endswith(ext):
        nome += ext

    id_sessao = str(uuid.uuid4())
    storage = StorageService()
    storage_path = f"temporario/{id_sessao}/{nome}"
    content_type = f"application/{ext.lstrip('.')}" if ext == ".pdf" else f"image/{ext.lstrip('.')}"
    await storage.upload_file(content, storage_path, content_type)

    try:
        if hasattr(orchestrate_new_inquerito, "delay"):
            orchestrate_new_inquerito.delay([storage_path], [nome_original])
        else:
            raise HTTPException(status_code=503, detail="Serviço de processamento (Celery/Redis) indisponível.")
        logger.info(f"[INGESTÃO-URL] Orquestrador acionado para {nome_original} — sessão {id_sessao}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Não foi possível iniciar o processamento: {str(e)}")

    return IngestaoIniciaResponse(
        id_sessao=id_sessao,
        status="processando",
        mensagem=f"Arquivo '{nome_original}' baixado do OneDrive. O Orquestrador IA está analisando para criar o inquérito automaticamente.",
        arquivos_recebidos=[nome_original],
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

    sync_engine = create_engine(_s.DATABASE_URL_SYNC, pool_size=1, max_overflow=0)
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


# ── Admin: Relatório Inicial em Lote ──────────────────────────────────────────

@router.post("/admin/gerar-relatorio-inicial-lote", tags=["Admin"], status_code=200)
async def admin_gerar_relatorio_inicial_lote(forcar: bool = False):
    """
    Varre TODOS os inquéritos com documentos indexados e dispara o Relatório Inicial
    para aqueles que ainda não possuem um (ou todos, se forcar=true).

    Uso: POST /ingestao/admin/gerar-relatorio-inicial-lote?forcar=false
    Ideal para os inquéritos já ingeridos antes da implantação deste recurso.
    """
    from sqlalchemy import create_engine, select as sa_select, delete as sa_delete
    from sqlalchemy.orm import Session
    from app.core.config import settings as _s
    from app.core.database import _encode_password_in_url
    from app.models.inquerito import Inquerito
    from app.models.documento import Documento
    from app.models.documento_gerado import DocumentoGerado
    from app.workers.relatorio_inicial_task import gerar_relatorio_inicial_task
    import re as _re

    raw_url = _s.DATABASE_URL
    sync_url = _re.sub(r"^postgres(ql)?(\+asyncpg)?://", "postgresql://", raw_url)
    engine = create_engine(_encode_password_in_url(sync_url), pool_size=1, max_overflow=0)

    agendados = []
    pulados = []
    sem_docs = []

    with Session(engine) as db:
        # Todos os inquéritos
        inqueritos = db.execute(sa_select(Inquerito)).scalars().all()

        for inq in inqueritos:
            inq_id = inq.id

            # Verifica se tem documentos indexados
            docs = db.execute(
                sa_select(Documento)
                .where(Documento.inquerito_id == inq_id)
                .where(Documento.status_processamento == "concluido")
                .where(Documento.tipo_peca != "sintese_investigativa")
            ).scalars().all()

            if not docs:
                sem_docs.append(str(inq_id))
                continue

            # Verifica se já tem relatório inicial
            existente = db.execute(
                sa_select(DocumentoGerado)
                .where(DocumentoGerado.inquerito_id == inq_id)
                .where(DocumentoGerado.tipo == "relatorio_inicial")
                .limit(1)
            ).scalar_one_or_none()

            if existente and not forcar:
                pulados.append(str(inq_id))
                continue

            # Apaga o existente se forcar=true
            if existente and forcar:
                db.execute(
                    sa_delete(DocumentoGerado).where(
                        DocumentoGerado.inquerito_id == inq_id,
                        DocumentoGerado.tipo == "relatorio_inicial",
                    )
                )
                db.commit()

            gerar_relatorio_inicial_task.delay(str(inq_id))
            agendados.append({"inquerito_id": str(inq_id), "numero": inq.numero})

    engine.dispose()

    return {
        "status": "concluido",
        "agendados": len(agendados),
        "pulados_ja_tem": len(pulados),
        "sem_documentos": len(sem_docs),
        "inquéritos_agendados": agendados,
    }


# ── Admin: Reconciliação de Pipeline ─────────────────────────────────────────

@router.post("/admin/pipeline/reconciliar", tags=["Admin"])
async def admin_reconciliar_pipeline():
    """
    Dispara manualmente a reconciliação do pipeline de ingestão.

    Detecta e re-despacha automaticamente as tasks interrompidas:
      - Documentos sem peças extraídas
      - Documentos sem resumos hierárquicos
      - Inquéritos com todos os docs indexados mas sem Relatório Inicial
      - Inquéritos com Relatório Inicial mas sem Síntese Investigativa
      - Remove placeholders __PROCESSANDO__ travados (> 30 min)

    Normalmente executado automaticamente a cada 15 min pelo Celery Beat.
    Use este endpoint para forçar uma execução imediata após deploy ou restart.
    """
    from app.workers.reconcile_task import reconcile_pipeline_task
    task = reconcile_pipeline_task.delay()
    return {
        "status": "agendado",
        "task_id": task.id,
        "mensagem": (
            "Reconciliação de pipeline disparada. "
            "Verifique os logs do worker para detalhes das tasks re-despachadas."
        ),
    }


@router.post("/admin/{inquerito_id}/reextrair-pecas", tags=["Admin"])
async def admin_reextrair_pecas(inquerito_id: uuid.UUID):
    """
    Re-dispara extrair_pecas_task para todos os documentos de um inquérito
    que ainda não têm peças extraídas.

    Útil quando a extração automática foi interrompida (deploy, crash do worker).
    """
    import re as _re
    from sqlalchemy import create_engine, select as sa_select
    from sqlalchemy.orm import Session
    from app.core.config import settings as _s
    from app.core.database import _encode_password_in_url
    from app.models.documento import Documento
    from app.models.peca_extraida import PecaExtraida
    from app.workers.peca_extraction_task import extrair_pecas_task

    raw_url = _s.DATABASE_URL
    sync_url = _re.sub(r"^postgres(ql)?(\+asyncpg)?://", "postgresql://", raw_url)
    engine = create_engine(_encode_password_in_url(sync_url), pool_size=1, max_overflow=0)

    disparados = []
    ja_tem = []
    sem_texto = []

    with Session(engine) as db:
        docs = db.execute(
            sa_select(Documento)
            .where(Documento.inquerito_id == inquerito_id)
            .where(Documento.status_processamento == "concluido")
        ).scalars().all()

        if not docs:
            return {"ok": False, "mensagem": "Nenhum documento concluído para este inquérito."}

        for doc in docs:
            if not doc.texto_extraido or len(doc.texto_extraido.strip()) < 100:
                sem_texto.append(str(doc.id))
                continue

            existing = db.execute(
                sa_select(PecaExtraida)
                .where(PecaExtraida.documento_id == doc.id)
                .limit(1)
            ).scalar_one_or_none()

            if existing:
                ja_tem.append(str(doc.id))
                continue

            extrair_pecas_task.delay(str(doc.id), str(inquerito_id))
            disparados.append({"documento_id": str(doc.id), "nome": doc.nome_arquivo})

    engine.dispose()
    return {
        "ok": True,
        "inquerito_id": str(inquerito_id),
        "disparados": len(disparados),
        "ja_tinham_pecas": len(ja_tem),
        "sem_texto": len(sem_texto),
        "documentos_disparados": disparados,
    }
