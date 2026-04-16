"""
Escrivão AI — Task Celery: Geração de Resumos Hierárquicos
Executada após ingestão de documento para gerar e cachear resumos por nível.
Conforme blueprint §6.4 (Resumos Hierárquicos).
"""

import asyncio
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def generate_summaries_task(self, inquerito_id: str, documento_id: str):
    """
    Task Celery que gera os resumos hierárquicos de um documento.

    Fluxo:
    1. Resumo do Documento (texto completo → LLM Econômico)
    2. Resumo do Volume correspondente (consolida resumos de todos os docs do volume)
    3. Resumo do Caso (consolida resumos de todos os volumes)
    """
    logger.info(f"[RESUMO-TASK] Iniciando resumos — doc={documento_id}")

    async def _run():
        from app.models.documento import Documento
        from app.models.volume import Volume
        from app.models.inquerito import Inquerito
        from app.models.resumo_cache import ResumoCache
        from app.services.summary_service import SummaryService

        # Engine async dedicado pro worker
        async_url = _encode_password_in_url(settings.DATABASE_URL)
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        async_url = async_url.replace("postgres://", "postgresql+asyncpg://", 1)

        import ssl
        connect_args = {"statement_cache_size": 0}
        if "supabase" in async_url or "localhost" not in async_url:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx

        from sqlalchemy.pool import NullPool
        engine = create_async_engine(async_url, connect_args=connect_args, poolclass=NullPool)
        AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        service = SummaryService()

        doc_uuid = uuid.UUID(documento_id)
        inq_uuid = uuid.UUID(inquerito_id)

        async with AsyncSession_() as db:
            # ── 1. Resumo do documento ─────────────────────────
            doc = await db.get(Documento, doc_uuid)
            if not doc or not doc.texto_extraido:
                logger.warning(f"[RESUMO-TASK] Documento sem texto: {documento_id}")
                return {"status": "sem_texto"}

            await service.resumir_documento(
                db=db,
                inquerito_id=inq_uuid,
                documento_id=doc_uuid,
                texto=doc.texto_extraido,
                nome_arquivo=doc.nome_arquivo,
                tipo_peca=doc.tipo_peca or "outro",
            )

            # ── 2. Resumo do volume ────────────────────────────
            # Buscar todos os documentos do mesmo inquérito para consolidar
            result = await db.execute(
                select(Documento)
                .where(Documento.inquerito_id == inq_uuid)
                .where(Documento.status_processamento == "concluido")
            )
            todos_docs = result.scalars().all()

            # Buscar (ou gerar) resumo de cada documento
            resumos_docs = []
            for d in todos_docs:
                r_doc = await service.obter_resumo_documento(db, inq_uuid, d.id)
                if r_doc:
                    resumos_docs.append(f"### {d.nome_arquivo}\n{r_doc}")

            if resumos_docs:
                # Volume 1 por padrão se não houver separação por volumes
                # (suporte multi-volume pode ser adicionado depois)
                resumo_volume = await service.resumir_volume(
                    db=db,
                    inquerito_id=inq_uuid,
                    volume_id=inq_uuid,  # Usa o inquerito_id como volume_id único por ora
                    numero_volume=1,
                    resumos_documentos=resumos_docs,
                    forcar=True,  # Regerar pois um novo doc foi adicionado
                )

            # ── 3. Resumo executivo do caso ────────────────────
            inq = await db.get(Inquerito, inq_uuid)
            if inq:
                resumo_volume_final = await service.obter_resumo_documento(
                    db, inq_uuid, inq_uuid  # buscar volume
                ) or (resumos_docs[0] if resumos_docs else "")
                
                # Buscar resumo de volume que geramos no step anterior
                volume_cache_result = await db.execute(
                    select(ResumoCache)
                    .where(ResumoCache.inquerito_id == inq_uuid)
                    .where(ResumoCache.nivel == "volume")
                )
                vol_cache = volume_cache_result.scalar_one_or_none()
                resumo_vol_texto = vol_cache.texto_resumo if vol_cache else "\n".join(resumos_docs[:5])

                await service.resumir_caso(
                    db=db,
                    inquerito_id=inq_uuid,
                    numero_inquerito=inq.numero or str(inquerito_id),
                    resumos_volumes=[resumo_vol_texto],
                    forcar=True,  # Regerar sempre que nova doc é adicionada
                )

        await engine.dispose()

        # Atualizar documento sintético de análise (não bloqueia se falhar)
        try:
            generate_analise_task.delay(inquerito_id)
        except Exception as e:
            logger.warning(f"[RESUMO-TASK] Falha ao agendar análise analítica: {e}")

        return {"status": "concluido", "documento_id": documento_id}

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[RESUMO-TASK] Concluído — {result}")
        return result
    except Exception as e:
        logger.error(f"[RESUMO-TASK] Erro: {e}")
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60, time_limit=600, soft_time_limit=540)
def generate_analise_task(self, inquerito_id: str):
    """
    Gera (ou atualiza) a Síntese Investigativa do inquérito.

    Não reutiliza o ResumoCache — monta contexto completo com resumos de todos
    os documentos + personagens + cronologia e chama LLM premium com prompt
    investigativo de alto critério. Resultado salvo como Documento sintético
    visível junto das demais peças dos autos.
    """
    logger.info(f"[SINTESE-TASK] Iniciando — inquerito={inquerito_id}")

    async def _run():
        from app.models.inquerito import Inquerito
        from app.models.documento import Documento
        from app.models.pessoa import Pessoa
        from app.models.empresa import Empresa
        from app.models.evento_cronologico import EventoCronologico
        from app.models.documento_gerado import DocumentoGerado
        from app.services.summary_service import SummaryService
        from app.services.llm_service import LLMService
        from app.core.prompts import PROMPT_SINTESE_INVESTIGATIVA

        async_url = _encode_password_in_url(settings.DATABASE_URL)
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        async_url = async_url.replace("postgres://", "postgresql+asyncpg://", 1)

        import ssl
        connect_args = {"statement_cache_size": 0}
        if "supabase" in async_url or "localhost" not in async_url:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx

        from sqlalchemy.pool import NullPool
        engine = create_async_engine(async_url, connect_args=connect_args, poolclass=NullPool)
        AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        inq_uuid = uuid.UUID(inquerito_id)

        async with AsyncSession_() as db:
            inq = await db.get(Inquerito, inq_uuid)
            if not inq:
                logger.warning(f"[SINTESE-TASK] Inquérito não encontrado: {inquerito_id}")
                await engine.dispose()
                return {"status": "inquerito_nao_encontrado"}

            # ── 1. Resumos dos documentos reais ────────────────────────────────
            docs_result = await db.execute(
                select(Documento)
                .where(Documento.inquerito_id == inq_uuid)
                .where(Documento.status_processamento == "concluido")
                .where(Documento.tipo_peca != "sintese_investigativa")
            )
            todos_docs = docs_result.scalars().all()

            if not todos_docs:
                logger.warning(f"[SINTESE-TASK] Sem documentos indexados ainda: {inquerito_id}")
                await engine.dispose()
                raise Exception("sem_documentos_ainda")  # força retry com backoff

            service = SummaryService()
            resumos_partes = []
            docs_sem_resumo = []
            for d in todos_docs:
                r = await service.obter_resumo_documento(db, inq_uuid, d.id)
                if r:
                    resumos_partes.append(f"**{d.nome_arquivo}** (tipo: {d.tipo_peca or 'não classificado'})\n{r}")
                elif d.texto_extraido:
                    # Fallback: usa texto bruto truncado quando não há ResumoCache
                    trecho = d.texto_extraido[:3000]
                    resumos_partes.append(
                        f"**{d.nome_arquivo}** (tipo: {d.tipo_peca or 'não classificado'}) [sem resumo — texto bruto]\n{trecho}"
                    )
                    docs_sem_resumo.append(d.nome_arquivo)
                else:
                    docs_sem_resumo.append(f"{d.nome_arquivo} [sem texto extraído]")

            if docs_sem_resumo:
                logger.warning(
                    f"[SINTESE-TASK] {len(docs_sem_resumo)} doc(s) sem ResumoCache — usando texto bruto como fallback: "
                    + ", ".join(docs_sem_resumo)
                )

            if not resumos_partes:
                logger.error(
                    f"[SINTESE-TASK] FALHA TOTAL: {len(todos_docs)} doc(s) indexados mas nenhum tem texto extraído. "
                    f"Verifique o pipeline de OCR/extração para o inquérito {inquerito_id}."
                )
                await engine.dispose()
                raise Exception("sem_texto_extraido_em_nenhum_documento")  # força retry com backoff

            resumos_str = "\n\n---\n\n".join(resumos_partes)

            # ── 1b. Auto-substituição de número TEMP ────────────────────────────
            if inq.numero.startswith("TEMP-"):
                _IP_PATS = [
                    re.compile(r'\b(\d{3})[-.](\d{4,6})[/\-\.](\d{4})\b'),
                    re.compile(r'\bIP\s*[:\-]?\s*(\d{4,6})[/\-](\d{4})\b', re.IGNORECASE),
                    re.compile(r'\b(\d{4,6})[/\-](\d{4})\b'),
                ]
                numero_encontrado = None
                ano_encontrado = None
                for d in todos_docs:
                    if not d.texto_extraido:
                        continue
                    trecho = d.texto_extraido[:8000]
                    for pat in _IP_PATS:
                        m = pat.search(trecho)
                        if m:
                            grupos = m.groups()
                            if len(grupos) == 3:
                                numero_encontrado = f"{grupos[0]}-{grupos[1]}-{grupos[2]}"
                                ano_encontrado = int(grupos[2])
                            else:
                                numero_encontrado = f"{grupos[0]}-{grupos[1]}"
                                ano_encontrado = int(grupos[1])
                            break
                    if numero_encontrado:
                        break

                if numero_encontrado:
                    inq.numero = numero_encontrado
                    if not inq.ano:
                        inq.ano = ano_encontrado
                    await db.flush()
                    logger.info(f"[SINTESE-TASK] Número TEMP substituído por {numero_encontrado}")

            # ── 2. Personagens ─────────────────────────────────────────────────
            pessoas_result = await db.execute(
                select(Pessoa).where(Pessoa.inquerito_id == inq_uuid)
            )
            pessoas = pessoas_result.scalars().all()

            empresas_result = await db.execute(
                select(Empresa).where(Empresa.inquerito_id == inq_uuid)
            )
            empresas = empresas_result.scalars().all()

            personagens_linhas = []
            for p in pessoas:
                linha = f"- {p.nome} (CPF: {p.cpf or 'não informado'}) — {p.tipo_pessoa or 'papel não classificado'}"
                if p.observacoes:
                    linha += f" | Obs: {p.observacoes}"
                personagens_linhas.append(linha)
            for e in empresas:
                personagens_linhas.append(
                    f"- [EMPRESA] {e.nome} (CNPJ: {e.cnpj or 'não informado'}) — {e.tipo_empresa or 'tipo não classificado'}"
                )
            personagens_str = "\n".join(personagens_linhas) if personagens_linhas else "Nenhum personagem identificado nos autos."

            # ── 3. Cronologia ──────────────────────────────────────────────────
            eventos_result = await db.execute(
                select(EventoCronologico)
                .where(EventoCronologico.inquerito_id == inq_uuid)
                .order_by(EventoCronologico.data_fato)
            )
            eventos = eventos_result.scalars().all()

            cronologia_linhas = [
                f"- {ev.data_fato_str or str(ev.data_fato or 'data desconhecida')}: {ev.descricao}"
                for ev in eventos[:30]
            ]
            cronologia_str = "\n".join(cronologia_linhas) if cronologia_linhas else "Nenhum evento cronológico identificado."

            # ── 3b. Relatório Inicial (contexto estruturado prévio) ────────────
            relatorio_inicial_texto = ""
            try:
                rel_result = await db.execute(
                    select(DocumentoGerado)
                    .where(DocumentoGerado.inquerito_id == inq_uuid)
                    .where(DocumentoGerado.tipo == "relatorio_inicial")
                    .limit(1)
                )
                rel_doc = rel_result.scalar_one_or_none()
                if rel_doc and rel_doc.conteudo:
                    relatorio_inicial_texto = rel_doc.conteudo[:6000]
                    logger.info("[SINTESE-TASK] Relatório Inicial injetado como contexto")
            except Exception as _e:
                logger.warning(f"[SINTESE-TASK] Falha ao buscar Relatório Inicial (não crítico): {_e}")

            # ── 4. Montar prompt e chamar LLM premium ──────────────────────────
            numero = inq.numero or inquerito_id
            # Few-shot: buscar casos históricos similares (Banco de Casos Gold)
            casos_historicos_str = ""
            try:
                from app.services.casos_gold_service import CasosGoldService
                # Usa resumo do volume ou número do inquérito como query
                query_casos = resumos_str[:500] if resumos_str else numero
                casos_similares = await CasosGoldService().buscar_casos_similares(
                    query=query_casos, top_k=2
                )
                if casos_similares:
                    linhas = []
                    for c in casos_similares:
                        linhas.append(
                            f"**{c['titulo']}** ({c['tipo']}):\n{c['texto'][:600]}"
                        )
                    casos_historicos_str = "\n\n---\n\n".join(linhas)
                    logger.info(
                        f"[SINTESE-TASK] {len(casos_similares)} caso(s) histórico(s) injetado(s)"
                    )
            except Exception as _e:
                logger.warning(f"[SINTESE-TASK] Few-shot de casos falhou (não crítico): {_e}")

            prompt = PROMPT_SINTESE_INVESTIGATIVA.format(
                numero_inquerito=numero,
                relatorio_inicial=relatorio_inicial_texto or "Relatório Inicial ainda não gerado — use os resumos dos documentos abaixo.",
                casos_historicos=casos_historicos_str or "Nenhum caso histórico similar disponível.",
                resumos_documentos=resumos_str,
                personagens=personagens_str,
                cronologia=cronologia_str,
            )

            llm = LLMService()
            result_llm = await asyncio.wait_for(
                llm.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    tier="premium",
                    temperature=0.2,
                    max_tokens=4000,
                ),
                timeout=270,
            )
            sintese_texto = result_llm["content"].strip()

            # ── 5. Criar ou atualizar documento sintético ──────────────────────
            doc_result = await db.execute(
                select(Documento)
                .where(Documento.inquerito_id == inq_uuid)
                .where(Documento.tipo_peca == "sintese_investigativa")
            )
            doc_sintetico = doc_result.scalar_one_or_none()

            if doc_sintetico:
                doc_sintetico.texto_extraido = sintese_texto
            else:
                doc_sintetico = Documento(
                    inquerito_id=inq_uuid,
                    nome_arquivo="Síntese Investigativa",
                    tipo_peca="sintese_investigativa",
                    status_processamento="sintetico",
                    status_ocr="sintetico",
                    texto_extraido=sintese_texto,
                    total_paginas=1,
                )
                db.add(doc_sintetico)

            await db.commit()
            logger.info(f"[SINTESE-TASK] Síntese Investigativa salva — inquerito={inquerito_id}")

        await engine.dispose()
        return {"status": "concluido", "inquerito_id": inquerito_id}

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[SINTESE-TASK] Concluído — {result}")
        return result
    except Exception as e:
        logger.error(f"[SINTESE-TASK] Erro: {e}")
        raise self.retry(exc=e)
