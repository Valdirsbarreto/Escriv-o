"""
Escrivão AI — API: Inquéritos
Endpoints para CRUD de inquéritos, transição de estado e upload de documentos.
"""

import hashlib
import logging
import uuid
import re
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import select, func, text
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


# ── Parser de Delegacias ──────────────────────────────────────────

DELEGACIAS_MAP = {
    "911": {"nome": "Delegacia de Defraudações", "tipo": "especializada"},
    "912": {"nome": "Delegacia de Roubos e Furtos", "tipo": "especializada"},
    "913": {"nome": "Delegacia de Roubos e Furtos de Automóveis", "tipo": "especializada"},
    "914": {"nome": "Delegacia de Repressão a Entorpecentes", "tipo": "especializada"},
    "915": {"nome": "Delegacia de Homicídios da Capital", "tipo": "especializada"},
    "918": {"nome": "Delegacia de Crimes contra o Consumidor", "tipo": "especializada"},
    "919": {"nome": "Delegacia de Roubos e Furtos de Carga", "tipo": "especializada"},
    "920": {"nome": "Delegacia de Crimes contra o Meio Ambiente", "tipo": "especializada"},
    "921": {"nome": "Delegacia Fazendária", "tipo": "especializada"},
    "059": {"nome": "59ª DP Duque de Caxias", "tipo": "territorial"},
    "064": {"nome": "64ª DP São João de Meriti", "tipo": "territorial"},
    "072": {"nome": "72ª DP São Gonçalo", "tipo": "territorial"},
    "077": {"nome": "77ª DP Icaraí", "tipo": "territorial"},
    "105": {"nome": "105ª DP Petrópolis", "tipo": "territorial"},
}

def parse_inquerito(numero_ip: str):
    """Extrai informações do número do inquérito (formato RJ: DDD-NNNNNN/AAAA)"""
    match = re.match(r'^(\d{3})-(\d{1,6})/(\d{4})$', numero_ip.strip())
    if match:
        return {
            "delegacia_codigo": match.group(1),
            "sequencial": match.group(2),
            "ano": match.group(3)
        }
    return None


# ── CRUD ──────────────────────────────────────────────────────────


@router.post("", response_model=InqueritoResponse, status_code=201)
async def criar_inquerito(
    dados: InqueritoCreate,
    db: AsyncSession = Depends(get_db),
):
    """Cria um novo inquérito no estado 'recebido'."""
    origem_cod = None
    origem_nome = None
    
    parsed = parse_inquerito(dados.numero)
    if parsed:
        origem_cod = parsed["delegacia_codigo"]
        if not dados.ano:
            dados.ano = int(parsed["ano"])
        # Busca nome no dicionario
        deleg_info = DELEGACIAS_MAP.get(origem_cod)
        if deleg_info:
            origem_nome = deleg_info["nome"]

    # Inicialmente, se não for marcado como redistribuído via payload
    atual_cod = dados.delegacia_atual_codigo or origem_cod
    atual_nome = dados.delegacia_atual_nome or origem_nome
    if not dados.redistribuido:
        atual_cod = origem_cod
        atual_nome = origem_nome

    inquerito = Inquerito(
        numero=dados.numero,
        delegacia=dados.delegacia,
        ano=dados.ano,
        descricao=dados.descricao,
        prioridade=dados.prioridade,
        classificacao_estrategica=dados.classificacao_estrategica,
        estado_atual=EstadoInquerito.RECEBIDO.value,
        delegacia_origem_codigo=origem_cod,
        delegacia_origem_nome=origem_nome,
        delegacia_atual_codigo=atual_cod,
        delegacia_atual_nome=atual_nome,
        redistribuido=dados.redistribuido,
    )
    db.add(inquerito)
    await db.flush()
    await db.refresh(inquerito)
    return inquerito


@router.get("", response_model=InqueritoListResponse)
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
    except Exception as e:
        logger.error(f"[INGESTÃO] Falha ao disparar ingestora ({e})")
        raise HTTPException(
            status_code=500,
            detail=f"Não foi possível iniciar o processamento do documento: {str(e)}"
        )

    return UploadResponse(
        documento_id=documento.id,
        nome_arquivo=file.filename,
        status="processando" if task_id else "enfileirado",
        mensagem="Documento recebido e enviado para processamento assíncrono.",
        task_id=task_id,
    )


@router.delete("/{inquerito_id}", status_code=204)
async def excluir_inquerito(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Exclui um inquérito e todos os seus dados (documentos, vetores, arquivos)."""
    result = await db.execute(
        select(Inquerito).where(Inquerito.id == inquerito_id)
    )
    inquerito = result.scalar_one_or_none()
    if not inquerito:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    # Remover arquivos do storage
    docs_result = await db.execute(
        select(Documento).where(Documento.inquerito_id == inquerito_id)
    )
    documentos = docs_result.scalars().all()
    storage = StorageService()
    for doc in documentos:
        try:
            await storage.delete_file(doc.storage_path)
        except Exception:
            pass

    # Remover vetores do Qdrant
    try:
        from app.services.qdrant_service import QdrantService
        qdrant = QdrantService()
        qdrant.delete_by_inquerito(str(inquerito_id))
    except Exception:
        pass

    # Deletar na ordem correta (respeitar FKs sem CASCADE no banco)
    iid = str(inquerito_id)
    await db.execute(text("DELETE FROM mensagens_chat WHERE sessao_id IN (SELECT id FROM sessoes_chat WHERE inquerito_id = :id)"), {"id": iid})
    await db.execute(text("DELETE FROM logs_ingestao WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM chunks WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM sessoes_chat WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM documentos WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM transicoes_estado WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM pessoas WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM empresas WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM contatos WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM enderecos WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM eventos_cronologicos WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM resultados_agentes WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM resumos_cache WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM tarefas_agentes WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM volumes WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM consultas_externas WHERE inquerito_id = :id"), {"id": iid})
    await db.execute(text("DELETE FROM inqueritos WHERE id = :id"), {"id": iid})
    await db.commit()


@router.post("/{inquerito_id}/reprocessar", status_code=200)
async def reprocessar_documentos_travados(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reprocessa documentos travados em 'processando' ou 'erro'."""
    result = await db.execute(
        select(Documento)
        .where(Documento.inquerito_id == inquerito_id)
        .where(Documento.status_processamento.in_(["processando", "erro"]))
    )
    travados = result.scalars().all()

    if not travados:
        return {"reprocessados": 0, "mensagem": "Nenhum documento travado encontrado."}

    from app.workers.ingestion import ingest_document

    count = 0
    for doc in travados:
        doc.status_processamento = "pendente"
        await db.flush()
        ingest_document.delay(str(doc.id), str(inquerito_id))
        count += 1

    await db.commit()
    return {"reprocessados": count, "mensagem": f"{count} documento(s) reenfileirado(s) para processamento."}


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


@router.get("/{inquerito_id}/documentos/{documento_id}/conteudo")
async def conteudo_documento(
    inquerito_id: uuid.UUID,
    documento_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retorna o texto extraído e URL presignada para download do PDF original."""
    doc = await db.get(Documento, documento_id)
    if not doc or doc.inquerito_id != inquerito_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    download_url = None
    if doc.storage_path:
        try:
            from app.services.storage import StorageService
            storage = StorageService()
            download_url = storage.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": storage.bucket, "Key": doc.storage_path},
                ExpiresIn=3600,
            )
        except Exception:
            pass

    return {
        "id": str(doc.id),
        "nome_arquivo": doc.nome_arquivo,
        "tipo_peca": doc.tipo_peca,
        "status_processamento": doc.status_processamento,
        "texto_extraido": doc.texto_extraido or "",
        "total_paginas": doc.total_paginas,
        "download_url": download_url,
    }


@router.patch("/{inquerito_id}/numero")
async def corrigir_numero(
    inquerito_id: uuid.UUID,
    dados: dict,
    db: AsyncSession = Depends(get_db),
):
    """Substitui manualmente o número do inquérito (útil para números TEMP-)."""
    novo_numero = (dados.get("numero") or "").strip()
    if not novo_numero:
        raise HTTPException(status_code=422, detail="Campo 'numero' é obrigatório")

    inq = await db.get(Inquerito, inquerito_id)
    if not inq:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    numero_anterior = inq.numero
    inq.numero = novo_numero

    # Tentar extrair ano do número (formato XXX-YYYYY-AAAA ou YYYYY-AAAA)
    m = re.search(r'[/\-](\d{4})$', novo_numero)
    if m and not inq.ano:
        inq.ano = int(m.group(1))

    await db.commit()
    logger.info(f"[INQUERITO] Número atualizado {numero_anterior} → {novo_numero} (id={inquerito_id})")
    return {"numero": novo_numero, "numero_anterior": numero_anterior}


@router.post("/{inquerito_id}/gerar-sintese")
async def gerar_sintese(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Dispara (ou re-dispara) a geração da Síntese Investigativa para um inquérito.
    Útil para inquéritos indexados antes do deploy do recurso.
    """
    inq = await db.get(Inquerito, inquerito_id)
    if not inq:
        raise HTTPException(status_code=404, detail="Inquérito não encontrado")

    docs_result = await db.execute(
        select(Documento)
        .where(Documento.inquerito_id == inquerito_id)
        .where(Documento.status_processamento == "concluido")
        .where(Documento.tipo_peca != "sintese_investigativa")
    )
    if not docs_result.scalars().all():
        raise HTTPException(status_code=422, detail="Nenhum documento indexado neste inquérito")

    from app.workers.summary_task import generate_analise_task
    generate_analise_task.delay(str(inquerito_id))

    return {"status": "agendado", "mensagem": "Síntese Investigativa em geração. Aguarde alguns minutos."}


@router.get("/{inquerito_id}/progresso")
async def progresso_pipeline(
    inquerito_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna o progresso em tempo real do pipeline de ingestão.
    Inclui status por documento (última etapa registrada) e estado da Síntese Investigativa.
    """
    from app.models.log_ingestao import LogIngestao

    # Documentos reais (excluindo sintético)
    docs_result = await db.execute(
        select(Documento)
        .where(Documento.inquerito_id == inquerito_id)
        .where(Documento.tipo_peca != "sintese_investigativa")
        .order_by(Documento.created_at)
    )
    docs = docs_result.scalars().all()

    total = len(docs)
    if total == 0:
        return {"total": 0, "concluidos": 0, "percentual": 0, "docs": [], "sintese_pronta": False}

    # Última etapa de cada documento via LogIngestao
    ETAPAS_ORDEM = [
        "download", "extracao", "chunking", "embedding",
        "indexacao", "extracao_entidades", "resumos_agendados", "pipeline_completo",
    ]

    docs_info = []
    concluidos = 0
    erros = 0

    for doc in docs:
        logs_result = await db.execute(
            select(LogIngestao)
            .where(LogIngestao.documento_id == doc.id)
            .order_by(LogIngestao.created_at.desc())
            .limit(1)
        )
        ultimo_log = logs_result.scalar_one_or_none()

        ultima_etapa = ultimo_log.etapa if ultimo_log else None
        ultima_status = ultimo_log.status if ultimo_log else None

        # Progresso dentro do doc (0–8)
        etapa_idx = ETAPAS_ORDEM.index(ultima_etapa) + 1 if ultima_etapa in ETAPAS_ORDEM else 0
        doc_pct = round((etapa_idx / len(ETAPAS_ORDEM)) * 100)

        if doc.status_processamento == "concluido":
            concluidos += 1
            doc_pct = 100
        elif doc.status_processamento == "erro":
            erros += 1

        docs_info.append({
            "id": str(doc.id),
            "nome": doc.nome_arquivo,
            "status": doc.status_processamento,
            "ultima_etapa": ultima_etapa,
            "ultima_etapa_status": ultima_status,
            "percentual": doc_pct,
        })

    # Síntese Investigativa
    sintese_result = await db.execute(
        select(Documento)
        .where(Documento.inquerito_id == inquerito_id)
        .where(Documento.tipo_peca == "sintese_investigativa")
    )
    sintese_pronta = sintese_result.scalar_one_or_none() is not None

    # Percentual geral: 90% para indexação + 10% para síntese
    base_pct = round((concluidos / total) * 90)
    percentual = base_pct + (10 if sintese_pronta else 0)

    return {
        "total": total,
        "concluidos": concluidos,
        "processando": sum(1 for d in docs if d.status_processamento == "processando"),
        "pendentes": sum(1 for d in docs if d.status_processamento == "pendente"),
        "erros": erros,
        "percentual": percentual,
        "sintese_pronta": sintese_pronta,
        "docs": docs_info,
    }
