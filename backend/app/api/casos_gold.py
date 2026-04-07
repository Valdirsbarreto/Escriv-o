"""
Escrivão AI — API: Banco de Casos Gold (Pilar B — Faro Investigativo)
Endpoints admin para ingestão, listagem e remoção de casos históricos.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/casos-gold", tags=["Casos Gold — Admin"])


def _check_admin(x_admin_secret: str) -> None:
    """Verifica autenticação admin via X-Admin-Secret header."""
    if x_admin_secret != settings.APP_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Acesso não autorizado")


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/ingerir")
async def ingerir_caso(
    file: UploadFile = File(..., description="Arquivo PDF ou TIFF do caso histórico"),
    titulo: str = Form(..., description="Título do caso (ex: 'Sentença Caso Furto Qualificado 2023')"),
    tipo: str = Form(
        ...,
        description=(
            "Tipo do caso: sentenca_condenatoria | sentenca_absolutoria | acordao_tjsp | "
            "laudo_pericial_referencia | relatorio_policial_modelo | outro"
        ),
    ),
    fonte: Optional[str] = Form(default=None, description="Fonte do documento (ex: TJSP, DEIC)"),
    ano: Optional[int] = Form(default=None, description="Ano do documento"),
    x_admin_secret: str = Header(default=""),
):
    """
    Ingere um novo caso histórico (PDF) no Banco de Casos Gold.

    Salva o PDF no S3 com prefixo `casos_gold/`, dispara task Celery de processamento
    e retorna o caso_id imediatamente.

    Requer header: X-Admin-Secret == APP_SECRET_KEY
    """
    _check_admin(x_admin_secret)

    # Validar tipo
    tipos_validos = {
        "sentenca_condenatoria",
        "sentenca_absolutoria",
        "acordao_tjsp",
        "laudo_pericial_referencia",
        "relatorio_policial_modelo",
        "outro",
    }
    if tipo not in tipos_validos:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo inválido. Use um de: {sorted(tipos_validos)}",
        )

    if not file.filename or not file.filename.lower().endswith((".pdf", ".tif", ".tiff")):
        raise HTTPException(status_code=422, detail="Apenas arquivos PDF ou TIFF são aceitos")

    # Ler conteúdo do upload
    try:
        conteudo = await file.read()
    except Exception as e:
        logger.error(f"[CASOS-GOLD-API] Erro ao ler arquivo: {e}")
        raise HTTPException(status_code=500, detail="Erro ao ler arquivo enviado")

    if not conteudo:
        raise HTTPException(status_code=422, detail="Arquivo vazio")

    # Gerar caso_id e s3_key
    caso_id = str(uuid.uuid4())
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "pdf"
    s3_key = f"casos_gold/{caso_id}.{ext}"

    # Upload para S3
    try:
        from app.services.storage import StorageService
        storage = StorageService()
        await storage.upload_file(
            content=conteudo,
            key=s3_key,
            content_type=file.content_type or "application/octet-stream",
        )
        logger.info(f"[CASOS-GOLD-API] Arquivo salvo em S3: {s3_key}")
    except Exception as e:
        logger.error(f"[CASOS-GOLD-API] Erro ao salvar no S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo no S3: {e}")

    # Montar metadata
    metadata: dict = {}
    if fonte:
        metadata["fonte"] = fonte
    if ano:
        metadata["ano"] = ano

    # Disparar task Celery
    try:
        from app.workers.casos_gold_task import processar_caso_gold
        processar_caso_gold.delay(
            caso_id=caso_id,
            s3_key=s3_key,
            titulo=titulo,
            tipo=tipo,
            metadata=metadata,
        )
        logger.info(f"[CASOS-GOLD-API] Task Celery disparada — caso_id={caso_id}")
    except Exception as e:
        logger.error(f"[CASOS-GOLD-API] Erro ao disparar task Celery: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao agendar processamento: {e}")

    return {"caso_id": caso_id, "status": "processando", "s3_key": s3_key}


@router.get("/")
async def listar_casos(
    x_admin_secret: str = Header(default=""),
):
    """
    Lista os últimos 50 casos indexados no Banco de Casos Gold.

    Requer header: X-Admin-Secret == APP_SECRET_KEY
    """
    _check_admin(x_admin_secret)

    try:
        from app.services.casos_gold_service import CasosGoldService
        service = CasosGoldService()
        casos = service.listar_casos(limit=50)
    except Exception as e:
        logger.error(f"[CASOS-GOLD-API] Erro ao listar casos: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar Qdrant: {e}")

    return {"total": len(casos), "casos": casos}


@router.delete("/{caso_id}")
async def deletar_caso(
    caso_id: str,
    x_admin_secret: str = Header(default=""),
):
    """
    Remove todos os vetores de um caso pelo seu caso_id.

    Requer header: X-Admin-Secret == APP_SECRET_KEY
    """
    _check_admin(x_admin_secret)

    # Validar formato UUID
    try:
        uuid.UUID(caso_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="caso_id deve ser um UUID válido")

    try:
        from app.services.casos_gold_service import CasosGoldService
        service = CasosGoldService()
        total_removido = service.deletar_caso(caso_id)
    except Exception as e:
        logger.error(f"[CASOS-GOLD-API] Erro ao deletar caso {caso_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao remover caso: {e}")

    if total_removido == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhum vetor encontrado para caso_id={caso_id}",
        )

    return {
        "caso_id": caso_id,
        "status": "removido",
        "pontos_removidos": total_removido,
    }
