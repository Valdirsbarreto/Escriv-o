"""
Escrivão AI — Task de Ingestão de Documentos (Sprint 2)
Pipeline assíncrono completo: extração → OCR seletivo → chunking → embeddings → Qdrant.
Conforme blueprint §6.1 (Document Ingestion Pipeline).
"""

import logging
import time
import uuid
from datetime import datetime

import unicodedata
import re

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.workers.celery_app import celery_app
from app.services.pdf_extractor import PDFExtractorService
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

# Engine síncrono para uso dentro do worker Celery
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_size=1,
    max_overflow=1,   # máx 2 conexões por worker — Supabase free tier
    pool_pre_ping=True,
    pool_recycle=300,
)

# Prioridade de tipo de pessoa (maior = mais específico)
_TIPO_PRIORIDADE = {"investigado": 4, "vitima": 3, "testemunha": 2, "outro": 1}


def _normalizar_nome(nome: str) -> str:
    """Remove acentos, espaços extras e converte para minúsculas para comparação."""
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = re.sub(r"\s+", " ", nome).strip().lower()
    return nome


def _upsert_pessoa(db: Session, inquerito_id: uuid.UUID, p_dict: dict) -> None:
    """
    Insere ou atualiza uma Pessoa dentro do mesmo inquérito.
    Prioridade de deduplicação: CPF > nome normalizado.
    Atualiza tipo_pessoa para o mais específico entre o existente e o novo.
    """
    from app.models.pessoa import Pessoa

    nome_raw = (p_dict.get("nome") or "Desconhecido")[:300]
    cpf = (p_dict.get("cpf") or "").strip()[:14]
    tipo_novo = (p_dict.get("tipo") or "outro")[:50].lower()
    nome_norm = _normalizar_nome(nome_raw)

    # Tentar achar pelo CPF primeiro (mais confiável)
    existente = None
    if cpf:
        existente = db.execute(
            select(Pessoa)
            .where(Pessoa.inquerito_id == inquerito_id)
            .where(Pessoa.cpf == cpf)
        ).scalar_one_or_none()

    # Se não achou por CPF, tenta por nome normalizado
    if not existente:
        candidatos = db.execute(
            select(Pessoa)
            .where(Pessoa.inquerito_id == inquerito_id)
        ).scalars().all()

        for c in candidatos:
            if _normalizar_nome(c.nome) == nome_norm:
                existente = c
                break

    obs_nova = (p_dict.get("observacoes") or "").strip() or None

    if existente:
        # Atualiza CPF se ainda não tinha
        if cpf and not existente.cpf:
            existente.cpf = cpf
        # Atualiza tipo para o mais específico
        tipo_atual = (existente.tipo_pessoa or "outro").lower()
        if _TIPO_PRIORIDADE.get(tipo_novo, 0) > _TIPO_PRIORIDADE.get(tipo_atual, 0):
            existente.tipo_pessoa = tipo_novo
        # Acumula observações únicas
        if obs_nova:
            obs_atual = existente.observacoes or ""
            if obs_nova not in obs_atual:
                existente.observacoes = (obs_atual + "; " + obs_nova).strip("; ")
    else:
        db.add(Pessoa(
            inquerito_id=inquerito_id,
            nome=nome_raw,
            cpf=cpf or None,
            tipo_pessoa=tipo_novo,
            observacoes=obs_nova,
        ))


def _upsert_empresa(db: Session, inquerito_id: uuid.UUID, e_dict: dict) -> None:
    """Insere ou atualiza Empresa (deduplicação por CNPJ > nome normalizado)."""
    from app.models.empresa import Empresa

    nome_raw = (e_dict.get("nome") or "Desconhecida")[:300]
    cnpj = (e_dict.get("cnpj") or "").strip()[:18]
    tipo = (e_dict.get("tipo") or "outro")[:50]
    nome_norm = _normalizar_nome(nome_raw)

    existente = None
    if cnpj:
        existente = db.execute(
            select(Empresa)
            .where(Empresa.inquerito_id == inquerito_id)
            .where(Empresa.cnpj == cnpj)
        ).scalar_one_or_none()

    if not existente:
        candidatos = db.execute(
            select(Empresa).where(Empresa.inquerito_id == inquerito_id)
        ).scalars().all()
        for c in candidatos:
            if _normalizar_nome(c.nome) == nome_norm:
                existente = c
                break

    if existente:
        if cnpj and not existente.cnpj:
            existente.cnpj = cnpj
    else:
        db.add(Empresa(
            inquerito_id=inquerito_id,
            nome=nome_raw,
            cnpj=cnpj or None,
            tipo_empresa=tipo,
        ))


def _log_etapa(db: Session, documento_id: str, inquerito_id: str,
               etapa: str, status: str, detalhes: str = None,
               duracao_ms: int = None, dados_extras: dict = None):
    """Registra uma etapa no log de ingestão."""
    from app.models.log_ingestao import LogIngestao
    log = LogIngestao(
        documento_id=uuid.UUID(documento_id),
        inquerito_id=uuid.UUID(inquerito_id),
        etapa=etapa,
        status=status,
        detalhes=detalhes,
        duracao_ms=duracao_ms,
        dados_extras=dados_extras,
    )
    db.add(log)
    db.commit()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document(self, documento_id: str, inquerito_id: str):
    """
    Pipeline de ingestão assíncrona de um documento.

    Etapas (conforme blueprint §6.1):
    1. Download do arquivo do storage
    2. Extração de texto nativo (pypdf)
    3. OCR seletivo nas páginas sem texto confiável
    4. Divisão em chunks (500-800 palavras)
    5. Geração de embeddings (sentence-transformers)
    6. Indexação no Qdrant com metadados
    7. [FUTURO Sprint 4] Classificação do tipo de peça
    8. [FUTURO Sprint 4] Extração de entidades
    9. [FUTURO Sprint 5] Resumos hierárquicos
    10. Atualização do status no PostgreSQL
    """
    from app.models.inquerito import Inquerito
    from app.models.documento import Documento
    from app.models.chunk import Chunk
    from app.core.state_machine import EstadoInquerito
    from app.models.estado_inquerito import TransicaoEstado

    logger.info(f"[INGESTÃO] Iniciando documento {documento_id} do inquérito {inquerito_id}")
    pipeline_start = time.time()

    try:
        with Session(sync_engine) as db:
            # ── Buscar documento ──────────────────────────────
            doc = db.execute(
                select(Documento).where(Documento.id == uuid.UUID(documento_id))
            ).scalar_one_or_none()

            if not doc:
                logger.error(f"Documento {documento_id} não encontrado")
                return {"status": "erro", "mensagem": "Documento não encontrado"}

            doc.status_processamento = "processando"
            db.commit()

            # ── 1. Download do arquivo ────────────────────────
            t0 = time.time()
            logger.info(f"[INGESTÃO] Baixando arquivo: {doc.storage_path}")
            storage = StorageService()

            try:
                import asyncio
                loop = asyncio.new_event_loop()
                content = loop.run_until_complete(storage.download_file(doc.storage_path))
                loop.close()
            except Exception as e:
                _log_etapa(db, documento_id, inquerito_id, "download", "erro",
                           detalhes=str(e))
                logger.error(f"Erro ao baixar arquivo: {e}")
                doc.status_processamento = "erro"
                db.commit()
                raise self.retry(exc=e)

            _log_etapa(db, documento_id, inquerito_id, "download", "concluido",
                       duracao_ms=int((time.time() - t0) * 1000),
                       dados_extras={"tamanho_bytes": len(content)})

            # ── 2. Extração de texto + OCR seletivo (ou OCR de imagem) ───────────
            t0 = time.time()
            logger.info("[INGESTÃO] Extraindo texto do documento")
            
            content_type = "application/pdf"
            ext = doc.storage_path.rsplit(".", 1)[-1].lower() if "." in doc.storage_path else "pdf"
            if ext in ("tif", "tiff"):
                content_type = "image/tiff"
            elif ext in ("jpg", "jpeg"):
                content_type = "image/jpeg"
            elif ext == "png":
                content_type = "image/png"

            pdf_service = PDFExtractorService()
            extraction = pdf_service.extract_any_file(content, content_type)

            doc.total_paginas = extraction["total_paginas"]
            doc.texto_extraido = extraction["texto_completo"][:100000]

            paginas_ocr = [
                p["numero"] for p in extraction["paginas"]
                if p.get("origem") == "ocr"
            ]
            paginas_pendentes = [
                p["numero"] for p in extraction["paginas"]
                if p.get("precisa_ocr", False)
            ]

            if paginas_pendentes:
                doc.status_ocr = "parcial"
            elif paginas_ocr:
                doc.status_ocr = "completo_com_ocr"
            else:
                doc.status_ocr = "completo"

            db.commit()

            _log_etapa(db, documento_id, inquerito_id, "extracao", "concluido",
                       duracao_ms=int((time.time() - t0) * 1000),
                       dados_extras={
                           "total_paginas": extraction["total_paginas"],
                           "paginas_ocr": len(paginas_ocr),
                           "paginas_pendentes": len(paginas_pendentes),
                       })

            # ── 3. Chunking ──────────────────────────────────
            t0 = time.time()
            logger.info("[INGESTÃO] Dividindo em chunks")
            chunks_data = pdf_service.chunk_text(
                extraction["paginas"],
                chunk_size=600,
                overlap=100,
            )

            logger.info(f"[INGESTÃO] {len(chunks_data)} chunks gerados")

            _log_etapa(db, documento_id, inquerito_id, "chunking", "concluido",
                       duracao_ms=int((time.time() - t0) * 1000),
                       dados_extras={"total_chunks": len(chunks_data)})

            # ── 4. Salvar chunks no PostgreSQL ────────────────
            chunk_records = []
            for chunk_data in chunks_data:
                chunk = Chunk(
                    inquerito_id=uuid.UUID(inquerito_id),
                    documento_id=uuid.UUID(documento_id),
                    pagina_inicial=chunk_data["pagina_inicial"],
                    pagina_final=chunk_data["pagina_final"],
                    texto=chunk_data["texto"],
                )
                db.add(chunk)
                chunk_records.append(chunk)

            db.commit()

            # Refresh para obter IDs
            for chunk in chunk_records:
                db.refresh(chunk)

            # ── 5. Embeddings ─────────────────────────────────
            t0 = time.time()
            logger.info(f"[INGESTÃO] Gerando embeddings para {len(chunk_records)} chunks")

            try:
                from app.services.embedding_service import EmbeddingService

                embedding_service = EmbeddingService()
                textos = [c.texto for c in chunk_records]
                embeddings = embedding_service.generate_batch(textos, batch_size=64)

                for chunk, embedding in zip(chunk_records, embeddings):
                    chunk.embedding_model = "text-embedding-004"

                db.commit()

                _log_etapa(db, documento_id, inquerito_id, "embedding", "concluido",
                           duracao_ms=int((time.time() - t0) * 1000),
                           dados_extras={
                               "total_embeddings": len(embeddings),
                               "modelo": "text-embedding-004",
                               "dimensoes": 768,
                           })

            except Exception as e:
                logger.warning(f"[INGESTÃO] Embeddings falharam: {e}")
                _log_etapa(db, documento_id, inquerito_id, "embedding", "erro",
                           detalhes=str(e),
                           duracao_ms=int((time.time() - t0) * 1000))
                embeddings = None

            # ── 6. Indexação no Qdrant ────────────────────────
            if embeddings:
                t0 = time.time()
                logger.info("[INGESTÃO] Indexando no Qdrant")

                try:
                    from app.services.qdrant_service import QdrantService

                    qdrant = QdrantService()
                    qdrant.ensure_collection(vector_size=768)

                    points = [
                        {
                            "id": str(chunk.id),
                            "vector": embedding,
                            "payload": {
                                "inquerito_id": inquerito_id,
                                "documento_id": documento_id,
                                "chunk_id": str(chunk.id),
                                "pagina_inicial": chunk.pagina_inicial,
                                "pagina_final": chunk.pagina_final,
                                "tipo_documento": chunk.tipo_documento or "",
                                "texto_preview": chunk.texto[:500],
                            },
                        }
                        for chunk, embedding in zip(chunk_records, embeddings)
                    ]

                    total_indexado = qdrant.upsert_chunks(points)

                    # Atualizar qdrant_point_id nos chunks
                    for chunk in chunk_records:
                        chunk.qdrant_point_id = str(chunk.id)
                    db.commit()

                    _log_etapa(db, documento_id, inquerito_id, "indexacao", "concluido",
                               duracao_ms=int((time.time() - t0) * 1000),
                               dados_extras={"total_indexado": total_indexado})

                except Exception as e:
                    logger.warning(f"[INGESTÃO] Indexação Qdrant falhou: {e}")
                    _log_etapa(db, documento_id, inquerito_id, "indexacao", "erro",
                               detalhes=str(e),
                               duracao_ms=int((time.time() - t0) * 1000))

            # ── 7. Classificação e 8. Extração de Identidades (NER) ────────────
            t0 = time.time()
            logger.info("[INGESTÃO] Executando Extrator LLM Econômico (Classificação e NER)")
            try:
                from app.services.extractor_service import ExtractorService
                from app.models.endereco import Endereco
                from app.models.contato import Contato
                from app.models.evento_cronologico import EventoCronologico
                
                extractor = ExtractorService()
                texto_analise = extraction["texto_completo"]
                
                import asyncio
                # Executar corrotinas no sync context
                loop = asyncio.new_event_loop()
                async def run_extraction():
                    cat = await extractor.classificar_documento(texto_analise)
                    ent = await extractor.extrair_entidades(texto_analise)
                    return cat, ent
                
                categoria, entidades = loop.run_until_complete(run_extraction())
                loop.close()

                if entidades is None:
                    entidades = {}

                doc.tipo_peca = categoria
                logger.info(f"[INGESTÃO] Documento classificado como: {categoria}")

                # Enriquecer payload Qdrant com tipo_peca (para busca filtrada por tipo)
                try:
                    from app.services.qdrant_service import QdrantService as _QS
                    _QS().set_payload_by_documento(documento_id, {"tipo_peca": categoria})
                except Exception as _qe:
                    logger.warning(f"[INGESTÃO] Falha ao atualizar tipo_peca no Qdrant: {_qe}")
                
                # Upsert de entidades (deduplicação por CPF > nome normalizado)
                inquerito_uuid = uuid.UUID(inquerito_id)
                for p_dict in entidades.get("pessoas", []) or []:
                    _upsert_pessoa(db, inquerito_uuid, p_dict)
                for e_dict in entidades.get("empresas", []) or []:
                    _upsert_empresa(db, inquerito_uuid, e_dict)
                for end_dict in entidades.get("enderecos", []) or []:
                    db.add(Endereco(
                        inquerito_id=uuid.UUID(inquerito_id),
                        endereco_completo=(end_dict.get("endereco_completo") or "Não informado"),
                        cidade=(end_dict.get("cidade") or "")[:100],
                        estado=(end_dict.get("estado") or "")[:2],
                        cep=(end_dict.get("cep") or "")[:10]
                    ))
                for tel_dict in entidades.get("telefones", []) or []:
                    db.add(Contato(
                        inquerito_id=uuid.UUID(inquerito_id),
                        tipo_contato="telefone",
                        valor=(tel_dict.get("numero") or "")[:255]
                    ))
                for em_dict in entidades.get("emails", []) or []:
                    db.add(Contato(
                        inquerito_id=uuid.UUID(inquerito_id),
                        tipo_contato="email",
                        valor=(em_dict.get("endereco") or "")[:255]
                    ))
                for cron_dict in entidades.get("cronologia", []):
                    desc = cron_dict.get("descricao")
                    if desc:
                        db.add(EventoCronologico(
                            inquerito_id=uuid.UUID(inquerito_id),
                            data_fato_str=cron_dict.get("data", "")[:50],
                            descricao=desc,
                            documento_id=uuid.UUID(documento_id)
                        ))
                
                db.commit()
                _log_etapa(db, documento_id, inquerito_id, "extracao_entidades", "concluido",
                           duracao_ms=int((time.time() - t0) * 1000),
                           dados_extras={"categoria": categoria, "entidades_extraidas": len(entidades.get("pessoas", []))})
                           
            except Exception as e:
                logger.warning(f"[INGESTÃO] Falha na extração de entidades/classificação: {e}")
                _log_etapa(db, documento_id, inquerito_id, "extracao_entidades", "erro",
                           detalhes=str(e),
                           duracao_ms=int((time.time() - t0) * 1000))

            # ── 9. Disparar task de Resumos Hierárquicos (Sprint 5) ───────────
            try:
                from app.workers.summary_task import generate_summaries_task
                generate_summaries_task.delay(inquerito_id, documento_id)
                logger.info(f"[INGESTÃO] Task de resumos disparada para doc={documento_id}")
                _log_etapa(db, documento_id, inquerito_id, "resumos_agendados", "concluido",
                           dados_extras={"task": "generate_summaries_task"})
            except Exception as e:
                logger.warning(f"[INGESTÃO] Falha ao agendar resumos: {e}")

            # ── 9b. Disparar extração de peças individuais ────────────────────
            try:
                from app.workers.peca_extraction_task import extrair_pecas_task
                extrair_pecas_task.delay(documento_id, inquerito_id)
                logger.info(f"[INGESTÃO] Task de extração de peças disparada para doc={documento_id}")
            except Exception as e:
                logger.warning(f"[INGESTÃO] Falha ao agendar extração de peças: {e}")

            # ── 10. Atualizar status ──────────────────────────
            doc.status_processamento = "concluido"
            db.commit()

            # Atualizar inquérito
            inquerito = db.execute(
                select(Inquerito).where(Inquerito.id == uuid.UUID(inquerito_id))
            ).scalar_one_or_none()

            if inquerito:
                inquerito.total_paginas += extraction["total_paginas"]

                # Ativar modo grande se ultrapassar 1500 páginas
                if inquerito.total_paginas > 1500:
                    inquerito.modo_grande = True
                    logger.info("[INGESTÃO] Modo inquérito grande ativado (>1500 páginas)")

                # Verificar se todos os documentos foram processados
                docs_pendentes = db.execute(
                    select(Documento)
                    .where(Documento.inquerito_id == uuid.UUID(inquerito_id))
                    .where(Documento.status_processamento.in_(["pendente", "processando"]))
                ).scalars().all()

                if len(docs_pendentes) == 0:
                    if inquerito.estado_atual == EstadoInquerito.INDEXANDO.value:
                        estado_anterior = inquerito.estado_atual
                        inquerito.estado_atual = EstadoInquerito.TRIAGEM.value
                        transicao = TransicaoEstado(
                            inquerito_id=inquerito.id,
                            estado_anterior=estado_anterior,
                            estado_novo=EstadoInquerito.TRIAGEM.value,
                            motivo="Indexação completa de todos os documentos",
                        )
                        db.add(transicao)
                        logger.info("[INGESTÃO] Inquérito transitou para TRIAGEM")

                    # Disparar análise analítica automática quando todos os docs estão prontos
                    try:
                        from app.workers.summary_task import generate_analise_task
                        generate_analise_task.delay(inquerito_id)
                        logger.info(f"[INGESTÃO] Análise analítica agendada — inquerito={inquerito_id}")
                    except Exception as e:
                        logger.warning(f"[INGESTÃO] Falha ao agendar análise analítica: {e}")

                db.commit()

            duracao_total = int((time.time() - pipeline_start) * 1000)
            _log_etapa(db, documento_id, inquerito_id, "pipeline_completo", "concluido",
                       duracao_ms=duracao_total,
                       dados_extras={
                           "total_paginas": extraction["total_paginas"],
                           "total_chunks": len(chunks_data),
                           "paginas_ocr": len(paginas_ocr),
                           "embeddings_gerados": len(embeddings) if embeddings else 0,
                       })

            logger.info(
                f"[INGESTÃO] Documento {documento_id} processado em {duracao_total}ms — "
                f"{extraction['total_paginas']} págs, {len(chunks_data)} chunks"
            )

            return {
                "status": "concluido",
                "documento_id": documento_id,
                "total_paginas": extraction["total_paginas"],
                "total_chunks": len(chunks_data),
                "paginas_ocr": len(paginas_ocr),
                "embeddings_gerados": len(embeddings) if embeddings else 0,
                "duracao_ms": duracao_total,
            }

    except Exception as e:
        logger.error(f"[INGESTÃO] Erro no processamento: {e}")
        try:
            with Session(sync_engine) as db:
                _log_etapa(db, documento_id, inquerito_id, "pipeline_completo", "erro",
                           detalhes=str(e))
        except Exception:
            pass
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def reclassificar_documento(self, documento_id: str, inquerito_id: str):
    """
    Reclassifica um documento já indexado usando o texto salvo no banco.
    Atualiza tipo_peca no Postgres e nos payloads Qdrant — sem re-extrair PDF.
    """
    import asyncio
    from app.models.documento import Documento

    logger.info(f"[RECLASSIF] Iniciando reclassificação doc={documento_id}")
    try:
        with Session(sync_engine) as db:
            doc = db.execute(
                select(Documento).where(Documento.id == uuid.UUID(documento_id))
            ).scalar_one_or_none()

            if not doc or not doc.texto_extraido:
                logger.warning(f"[RECLASSIF] Documento {documento_id} não encontrado ou sem texto")
                return {"status": "ignorado", "motivo": "sem_texto"}

            texto_analise = doc.texto_extraido[:6000]

            from app.services.extractor_service import ExtractorService
            extractor = ExtractorService()

            loop = asyncio.new_event_loop()
            try:
                categoria = loop.run_until_complete(extractor.classificar_documento(texto_analise))
            finally:
                loop.close()

            doc.tipo_peca = categoria
            db.commit()
            logger.info(f"[RECLASSIF] doc={documento_id} → {categoria}")

            # Propagar para chunks Qdrant
            try:
                from app.services.qdrant_service import QdrantService
                QdrantService().set_payload_by_documento(documento_id, {"tipo_peca": categoria})
            except Exception as qe:
                logger.warning(f"[RECLASSIF] Falha ao atualizar Qdrant: {qe}")

            return {"status": "ok", "documento_id": documento_id, "tipo_peca": categoria}

    except Exception as e:
        logger.error(f"[RECLASSIF] Erro: {e}")
        raise self.retry(exc=e)
