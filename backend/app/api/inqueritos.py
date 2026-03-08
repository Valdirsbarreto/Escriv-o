"""
Escrivão AI — API: Inquéritos
Endpoints para CRUD de inquéritos, transição de estado e upload de documentos.
"""

import hashlib
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.state_machine import (
    EstadoInquerito,
    validar_transicao,
    obter_acoes_disponiveis,
    obter_transicoes_possiveis,
    DESCRICAO_ESTADOS,
)
from app.models.inquerito import Inquerito
from app.models.documento import Documento
from app.models.estado_inquerito import TransicaoEstado
from app.schemas.inquerito import (
    InqueritoCreate,
    InqueritoResponse,
    InqueritoListResponse,
    InqueritoUpdate,
    TransicaoEstadoRequest,
    TransicaoEstadoResponse,
    StatusInqueritoResponse,
    MenuInicialResponse,
)
from app.schemas.documento import DocumentoResponse, UploadResponse
from app.services.storage import StorageService

router = APIRouter(prefix="/inqueritos", tags=["Inquéritos"])


# ── CRUD ──────────────────────────────────────────────────────────


@router.post("/", response_model=InqueritoResponse, status_code=201)
async def criar_inquerito(
    dados: InqueritoCreate,
    db: AsyncSession = Depends(get_db),
):
    """Cria um novo inquérito no estado 'recebido'."""
    inquerito = Inquerito(
        numero=dados.numero,
        delegacia=dados.delegacia,
        ano=dados.ano,
        descricao=dados.descricao,
        prioridade=dados.prioridade,
        classificacao_estrategica=dados.classificacao_estrategica,
        estado_atual=EstadoInquerito.RECEBIDO.value,
    )
    db.add(inquerito)
    await db.flush()
    await db.refresh(inquerito)
    return inquerito


@router.get("/", response_model=InqueritoListResponse)
async def listar_inqueritos(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    db: AsyncSession = Depends(get_db),
):
    """Lista inquéritos com paginação e filtro opcional por estado."""
    query = select(Inquerito)
    count_query = select(func.count(Inquerito.id))

    if estado:
        query = query.where(Inquerito.estado_atual == estado)
        count_query = count_query.where(Inquerito.estado_atual == estado)

    query = query.order_by(Inquerito.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    inqueritos = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return InqueritoListResponse(items=inqueritos, total=total)


@router.get("/{inquerito_id}", response_model=InqueritoResponse)
async def obter_inquerito(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retorna detalhes de um inquérito."""
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")
    return inquerito


@router.patch("/{inquerito_id}", response_model=InqueritoResponse)
async def atualizar_inquerito(
    inquerito_id: uuid.UUID,
    dados: InqueritoUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Atualiza campos editáveis de um inquérito."""
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    update_data = dados.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(inquerito, field, value)

    await db.flush()
    await db.refresh(inquerito)
    return inquerito


# ── Status e Máquina de Estados ───────────────────────────────────


@router.get("/{inquerito_id}/status", response_model=StatusInqueritoResponse)
async def obter_status(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retorna o status do inquérito com ações e transições disponíveis."""
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    try:
        estado_enum = EstadoInquerito(inquerito.estado_atual)
        descricao = DESCRICAO_ESTADOS.get(estado_enum, "Estado desconhecido")
    except ValueError:
        descricao = "Estado desconhecido"

    return StatusInqueritoResponse(
        id=inquerito.id,
        numero=inquerito.numero,
        estado_atual=inquerito.estado_atual,
        descricao_estado=descricao,
        acoes_disponiveis=obter_acoes_disponiveis(inquerito.estado_atual),
        transicoes_possiveis=obter_transicoes_possiveis(inquerito.estado_atual),
        total_paginas=inquerito.total_paginas,
        total_documentos=inquerito.total_documentos,
        modo_grande=inquerito.modo_grande,
    )


@router.patch("/{inquerito_id}/estado", response_model=TransicaoEstadoResponse)
async def transitar_estado(
    inquerito_id: uuid.UUID,
    dados: TransicaoEstadoRequest,
    db: AsyncSession = Depends(get_db),
):
    """Realiza transição de estado do inquérito (valida regras da FSM)."""
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    estado_anterior = inquerito.estado_atual

    if not validar_transicao(estado_anterior, dados.novo_estado):
        transicoes = obter_transicoes_possiveis(estado_anterior)
        raise HTTPException(
            status_code=422,
            detail=f"Transição inválida: '{estado_anterior}' → '{dados.novo_estado}'. "
                   f"Transições possíveis: {transicoes}",
        )

    # Atualizar estado
    inquerito.estado_atual = dados.novo_estado

    # Registrar transição (trilha de auditoria)
    transicao = TransicaoEstado(
        inquerito_id=inquerito.id,
        estado_anterior=estado_anterior,
        estado_novo=dados.novo_estado,
        motivo=dados.motivo,
    )
    db.add(transicao)

    await db.flush()
    await db.refresh(transicao)
    return transicao


@router.get("/{inquerito_id}/menu", response_model=MenuInicialResponse)
async def obter_menu_inicial(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Menu de opções pós-carga do inquérito (§7.2 do blueprint).
    Retorna as opções disponíveis baseadas no estado atual.
    """
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    acoes = obter_acoes_disponiveis(inquerito.estado_atual)

    # Mapeia ações para opções amigáveis
    OPCOES_MAP = {
        "copiloto": {"id": "copiloto", "label": "Conversar com o Copiloto", "descricao": "Diálogo com o assistente investigativo"},
        "triagem_rapida": {"id": "triagem_rapida", "label": "Fazer triagem rápida", "descricao": "Visão panorâmica do procedimento"},
        "linhas_investigacao": {"id": "linhas_investigacao", "label": "Identificar linhas de investigação", "descricao": "Sugerir hipóteses investigativas plausíveis"},
        "perguntas_oitiva": {"id": "perguntas_oitiva", "label": "Preparar perguntas para oitivas", "descricao": "Elaborar roteiro de perguntas por perfil"},
        "osint_basico": {"id": "osint_basico", "label": "Levantar dados OSINT", "descricao": "Pesquisa em fontes abertas"},
        "osint_avancado": {"id": "osint_avancado", "label": "OSINT avançado (pivot, grafo)", "descricao": "Investigação digital aprofundada"},
        "sugerir_diligencias": {"id": "sugerir_diligencias", "label": "Sugerir diligências", "descricao": "Diligências úteis e proporcionais"},
        "verificar_prescricao": {"id": "verificar_prescricao", "label": "Verificar prescrição", "descricao": "Análise de prazos prescricionais"},
        "redigir_oficio": {"id": "redigir_oficio", "label": "Preparar ofício", "descricao": "Minuta de ofício para órgãos"},
        "redigir_despacho": {"id": "redigir_despacho", "label": "Preparar despacho", "descricao": "Minuta de despacho"},
        "representacao_cautelar": {"id": "representacao_cautelar", "label": "Representação cautelar", "descricao": "Minuta de representação por medida cautelar"},
        "relatorio_parcial": {"id": "relatorio_parcial", "label": "Relatório parcial", "descricao": "Relatório parcial do inquérito"},
        "relatorio_final": {"id": "relatorio_final", "label": "Relatório final", "descricao": "Relatório conclusivo do inquérito"},
        "tipificacao_provisoria": {"id": "tipificacao_provisoria", "label": "Tipificação provisória", "descricao": "Enquadramentos penais em tese"},
        "consultar_indices": {"id": "consultar_indices", "label": "Consultar índices", "descricao": "Pessoas, empresas, documentos e cronologia"},
        "consultar_documentos": {"id": "consultar_documentos", "label": "Consultar documentos", "descricao": "Busca nos autos indexados"},
        "upload_documentos": {"id": "upload_documentos", "label": "Enviar documentos", "descricao": "Upload de PDFs do inquérito"},
        "consultar_status_indexacao": {"id": "consultar_status_indexacao", "label": "Ver status da indexação", "descricao": "Acompanhar processamento dos documentos"},
    }

    opcoes = [OPCOES_MAP[a] for a in acoes if a in OPCOES_MAP]

    return MenuInicialResponse(
        mensagem=f"Inquérito {inquerito.numero} — O que deseja fazer?",
        opcoes=opcoes,
    )


# ── Upload de Documentos ─────────────────────────────────────────


@router.post("/{inquerito_id}/upload", response_model=UploadResponse)
async def upload_documento(
    inquerito_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload de documento PDF para um inquérito.
    O arquivo é salvo no MinIO e uma task de ingestão é disparada.
    """
    # Verificar inquérito
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    # Validar tipo de arquivo
    if not file.filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tiff")):
        raise HTTPException(
            status_code=400,
            detail="Formato não suportado. Use PDF, PNG, JPG ou TIFF.",
        )

    # Ler conteúdo e calcular hash
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    # Upload para MinIO/S3
    storage = StorageService()
    storage_path = f"inqueritos/{inquerito_id}/{file.filename}"
    await storage.upload_file(content, storage_path, file.content_type)

    # Criar registro do documento
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

    # Atualizar contadores do inquérito
    inquerito.total_documentos += 1

    # Transitar para INDEXANDO se estiver em RECEBIDO
    if inquerito.estado_atual == EstadoInquerito.RECEBIDO.value:
        estado_anterior = inquerito.estado_atual
        inquerito.estado_atual = EstadoInquerito.INDEXANDO.value
        transicao = TransicaoEstado(
            inquerito_id=inquerito.id,
            estado_anterior=estado_anterior,
            estado_novo=EstadoInquerito.INDEXANDO.value,
            motivo="Upload de documento iniciou indexação",
        )
        db.add(transicao)

    # Disparar task de ingestão assíncrona
    task_id = None
    try:
        from app.workers.ingestion import ingest_document
        result = ingest_document.delay(str(documento.id), str(inquerito_id))
        task_id = result.id
    except Exception:
        # Se o Celery não estiver disponível, marca para processamento posterior
        pass

    return UploadResponse(
        documento_id=documento.id,
        nome_arquivo=file.filename,
        status="processando" if task_id else "enfileirado",
        mensagem="Documento recebido e enviado para processamento assíncrono.",
        task_id=task_id,
    )


@router.get("/{inquerito_id}/documentos", response_model=list[DocumentoResponse])
async def listar_documentos(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os documentos de um inquérito."""
    result = await db.execute(
        select(Documento)
        .where(Documento.inquerito_id == inquerito_id)
        .order_by(Documento.created_at)
    )
    return result.scalars().all()
