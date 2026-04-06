"""
Escrivão AI — Serviço Copiloto Investigativo
RAG pipeline: query → embed → Qdrant → contexto → LLM → resposta com citações.
Conforme blueprint §7.3 e especificação §5.
"""

import logging
import time
import uuid
from typing import List, Dict, Optional, Any

from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService
from app.services.llm_service import LLMService
from app.core.prompts import (
    SYSTEM_PROMPT_COPILOTO,
    SYSTEM_PROMPT_AUDITORIA_FACTUAL,
    TEMPLATE_CONTEXTO_RAG,
)

logger = logging.getLogger(__name__)


class CopilotoService:
    """
    Copiloto investigativo conversacional com RAG.

    Fluxo:
    1. Usuário envia pergunta
    2. Gera embedding da query
    3. Busca chunks relevantes no Qdrant
    4. Monta contexto com citações
    5. Envia para o LLM com system prompt especializado
    6. [Opcional] Audita factualmente a resposta
    7. Retorna resposta com fontes
    """

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.qdrant_service = QdrantService()
        self.llm_service = LLMService()

    async def processar_mensagem(
        self,
        query: str,
        inquerito_id: str,
        historico: List[Dict[str, str]] = None,
        numero_inquerito: str = "",
        estado_atual: str = "",
        total_paginas: int = 0,
        total_documentos: int = 0,
        max_chunks: int = 15,
        auditar: bool = True,
        db=None,  # AsyncSession opcional para buscar resumo do caso
    ) -> Dict[str, Any]:
        """
        Processa uma mensagem do usuário e retorna resposta com fontes.

        Args:
            query: pergunta do usuário
            inquerito_id: UUID do inquérito
            historico: mensagens anteriores da sessão
            numero_inquerito: número para display
            estado_atual: estado do inquérito
            total_paginas: total de páginas indexadas
            total_documentos: total de documentos
            max_chunks: máximo de chunks de contexto
            auditar: se True, audita factualmente a resposta

        Returns:
            {
                "resposta": str,
                "fontes": [{"documento": str, "paginas": str, "score": float}],
                "auditoria": {...} ou None,
                "modelo": str,
                "tokens_prompt": int,
                "tokens_resposta": int,
                "custo_estimado": float,
                "tempo_total_ms": int,
            }
        """
        t_total = time.time()

        # ── 1. Busca RAG híbrida (vetor + full-text) ──────
        logger.info(f"[COPILOTO] Buscando contexto para: {query[:80]}...")

        query_vector = await self.embedding_service.agenerate(query)

        # Se o embedding falhou (retornou vetor nulo), pula busca RAG
        qdrant_ok = any(v != 0.0 for v in query_vector[:10])
        resultados = []
        if qdrant_ok:
            try:
                resultados = self.qdrant_service.search(
                    query_vector=query_vector,
                    limit=max_chunks,
                    inquerito_id=inquerito_id,
                )
            except Exception as e:
                logger.warning(f"[COPILOTO] Qdrant indisponível: {e} — respondendo sem RAG")

        # Busca textual complementar (detecta nomes/termos não surfaçados pelo vetor)
        if db is not None:
            try:
                text_hits = await self._busca_hibrida_texto(db, query, inquerito_id, limit=10)
                if text_hits:
                    # Deduplica: remove chunks que já vieram do Qdrant (por qdrant_point_id)
                    ids_qdrant = {
                        r.get("payload", {}).get("chunk_id", "")
                        for r in resultados
                    }
                    novos = [h for h in text_hits if h["payload"].get("chunk_id", "") not in ids_qdrant]
                    resultados = resultados + novos
                    logger.info(f"[COPILOTO] Busca híbrida: +{len(novos)} chunks de texto")
            except Exception as e:
                logger.warning(f"[COPILOTO] Busca híbrida falhou: {e}")

        # ── 2. Montar contexto ────────────────────────────
        contexto_partes = []
        fontes = []

        # Injetar resumo executivo do caso no topo do contexto (Sprint 5)
        if db is not None:
            try:
                from app.services.summary_service import SummaryService
                summary_svc = SummaryService()
                resumo_caso = await summary_svc.obter_resumo_caso(db, uuid.UUID(inquerito_id))
                if resumo_caso:
                    contexto_partes.append(
                        f"### Resumo Executivo do Inquérito\n{resumo_caso}\n\n---"
                    )
                    logger.info("[COPILOTO] Resumo do caso injetado no contexto RAG")
            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao buscar resumo do caso: {e}")

        # Injetar índice estruturado de pessoas e empresas (consulta direta ao banco)
        if db is not None:
            try:
                from sqlalchemy import select as sa_select
                from app.models.pessoa import Pessoa
                from app.models.empresa import Empresa

                pessoas_result = await db.execute(
                    sa_select(Pessoa)
                    .where(Pessoa.inquerito_id == uuid.UUID(inquerito_id))
                    .order_by(Pessoa.nome)
                )
                pessoas = pessoas_result.scalars().all()

                empresas_result = await db.execute(
                    sa_select(Empresa)
                    .where(Empresa.inquerito_id == uuid.UUID(inquerito_id))
                    .order_by(Empresa.nome)
                )
                empresas = empresas_result.scalars().all()

                if pessoas or empresas:
                    bloco = ["### Índice de Pessoas e Empresas Identificadas nos Autos\n"]

                    if pessoas:
                        bloco.append("**Pessoas físicas:**")
                        for p in pessoas:
                            papel = f" [{p.tipo_pessoa}]" if p.tipo_pessoa else ""
                            cpf = f" CPF: {p.cpf}" if p.cpf else ""
                            obs = f" — {p.observacoes}" if p.observacoes else ""
                            bloco.append(f"- {p.nome}{papel}{cpf}{obs}")

                    if empresas:
                        bloco.append("\n**Pessoas jurídicas:**")
                        for e in empresas:
                            tipo = f" [{e.tipo_empresa}]" if e.tipo_empresa else ""
                            cnpj = f" CNPJ: {e.cnpj}" if e.cnpj else ""
                            bloco.append(f"- {e.nome}{tipo}{cnpj}")

                    bloco.append("\n---")
                    contexto_partes.append("\n".join(bloco))
                    logger.info(f"[COPILOTO] Índice injetado: {len(pessoas)} pessoas, {len(empresas)} empresas")

            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao buscar índice de pessoas/empresas: {e}")

        # Injetar contatos (telefones/emails) e cronologia de eventos
        if db is not None:
            try:
                from sqlalchemy import select as sa_select  # noqa: F811
                from app.models.contato import Contato
                from app.models.evento_cronologico import EventoCronologico

                contatos_result = await db.execute(
                    sa_select(Contato)
                    .where(Contato.inquerito_id == uuid.UUID(inquerito_id))
                    .order_by(Contato.tipo_contato)
                )
                contatos = contatos_result.scalars().all()

                eventos_result = await db.execute(
                    sa_select(EventoCronologico)
                    .where(EventoCronologico.inquerito_id == uuid.UUID(inquerito_id))
                    .order_by(EventoCronologico.data_fato_str)
                )
                eventos = eventos_result.scalars().all()

                bloco_extra = []

                if contatos:
                    bloco_extra.append("### Telefones e E-mails Identificados nos Autos\n")
                    fones = [c for c in contatos if c.tipo_contato == "telefone"]
                    emails = [c for c in contatos if c.tipo_contato == "email"]
                    if fones:
                        bloco_extra.append("**Telefones:** " + ", ".join(c.valor for c in fones))
                    if emails:
                        bloco_extra.append("**E-mails:** " + ", ".join(c.valor for c in emails))
                    bloco_extra.append("---")

                if eventos:
                    bloco_extra.append("### Cronologia de Eventos\n")
                    for ev in eventos:
                        data = ev.data_fato_str or (ev.data_fato.strftime("%d/%m/%Y") if ev.data_fato else "Data não informada")
                        bloco_extra.append(f"- {data}: {ev.descricao}")
                    bloco_extra.append("---")

                if bloco_extra:
                    contexto_partes.append("\n".join(bloco_extra))
                    logger.info(f"[COPILOTO] Contatos/cronologia injetados: {len(contatos)} contatos, {len(eventos)} eventos")

            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao buscar contatos/cronologia: {e}")

        # Injetar documentos gerados pela IA (roteiros, ofícios, etc.)
        if db is not None:
            try:
                from sqlalchemy import select as sa_select  # noqa: F811
                from app.models.documento_gerado import DocumentoGerado

                docs_result = await db.execute(
                    sa_select(DocumentoGerado)
                    .where(DocumentoGerado.inquerito_id == uuid.UUID(inquerito_id))
                    .order_by(DocumentoGerado.created_at.desc())
                    .limit(10)
                )
                docs_gerados = docs_result.scalars().all()

                if docs_gerados:
                    bloco_docs = ["### Documentos Gerados pela IA (roteiros, ofícios, minutas)\n"]
                    for dg in docs_gerados:
                        data = dg.created_at.strftime("%d/%m/%Y") if dg.created_at else ""
                        bloco_docs.append(f"**[{dg.tipo.upper()}] {dg.titulo}** ({data})\n{dg.conteudo[:3000]}")
                        bloco_docs.append("---")
                    contexto_partes.insert(0, "\n".join(bloco_docs))
                    logger.info(f"[COPILOTO] {len(docs_gerados)} doc(s) gerado(s) injetado(s) no contexto")
            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao buscar docs gerados: {e}")

        for i, r in enumerate(resultados, 1):
            payload = r.get("payload", {})
            texto_preview = payload.get("texto_preview", "")
            documento = payload.get("documento_id", "documento")
            pagina_inicial = payload.get("pagina_inicial", 0)
            pagina_final = payload.get("pagina_final", 0)
            tipo_doc = payload.get("tipo_documento", "")

            contexto_partes.append(
                TEMPLATE_CONTEXTO_RAG.format(
                    indice=i,
                    score=r["score"],
                    documento=documento,
                    pagina_inicial=pagina_inicial,
                    pagina_final=pagina_final,
                    tipo_documento=tipo_doc or "não classificado",
                    texto=texto_preview,
                )
            )

            fontes.append({
                "documento_id": documento,
                "pagina_inicial": pagina_inicial,
                "pagina_final": pagina_final,
                "score": round(r["score"], 4),
                "tipo_documento": tipo_doc,
            })

        contexto_rag = "\n".join(contexto_partes) if contexto_partes else (
            "Nenhum contexto disponível ainda: documentos ainda não indexados ou coleção vetorial vazia. "
            "Responda com base no conhecimento geral sobre investigação policial e informe que os autos "
            "ainda não foram indexados para busca vetorial."
        )

        # ── 3. Montar mensagens ───────────────────────────
        system_prompt = SYSTEM_PROMPT_COPILOTO.format(
            numero_inquerito=numero_inquerito,
            estado_atual=estado_atual,
            total_paginas=total_paginas,
            total_documentos=total_documentos,
            contexto_rag=contexto_rag,
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Incluir histórico (últimas N mensagens para caber no contexto)
        if historico:
            # Limitar a últimas 10 trocas para não estourar contexto
            ultimas = historico[-20:]
            messages.extend(ultimas)

        messages.append({"role": "user", "content": query})

        # ── 4. Chamar LLM ────────────────────────────────
        logger.info("[COPILOTO] Enviando para LLM (premium)")

        try:
            llm_result = await self.llm_service.chat_completion(
                messages=messages,
                tier="premium",
                temperature=0.3,
                max_tokens=3000,
                agente="Copiloto",
            )
        except Exception as e:
            logger.error(f"[COPILOTO] LLM indisponível: {e}")
            return {
                "resposta": (
                    "⚠️ O serviço de LLM está temporariamente indisponível. "
                    "Por favor, verifique as configurações de API em .env e tente novamente.\n\n"
                    f"Erro: {str(e)[:200]}"
                ),
                "fontes": fontes,
                "auditoria": None,
                "modelo": "indisponível",
                "tokens_prompt": 0,
                "tokens_resposta": 0,
                "custo_estimado": 0.0,
                "tempo_total_ms": int((time.time() - t_total) * 1000),
            }

        resposta = llm_result["content"]

        # ── 5. Auditoria factual (opcional) ───────────────
        auditoria = None
        if auditar and fontes:
            try:
                auditoria = await self._auditar_resposta(resposta, contexto_rag)
            except Exception as e:
                logger.warning(f"[COPILOTO] Auditoria falhou: {e}")
                auditoria = {
                    "status": "erro",
                    "score_confiabilidade": None,
                    "recomendacao": "auditoria indisponível",
                }

        # ── 6. Resultado ──────────────────────────────────
        tempo_total = int((time.time() - t_total) * 1000)

        return {
            "resposta": resposta,
            "fontes": fontes,
            "auditoria": auditoria,
            "modelo": llm_result["model"],
            "tokens_prompt": llm_result["tokens_prompt"],
            "tokens_resposta": llm_result["tokens_resposta"],
            "custo_estimado": llm_result["custo_estimado"],
            "tempo_total_ms": tempo_total,
        }

    async def _busca_hibrida_texto(
        self,
        db,
        query: str,
        inquerito_id: str,
        limit: int = 10,
    ) -> list:
        """
        Busca full-text nos chunks armazenados no PostgreSQL.
        Extrai palavras da query e faz ILIKE (com normalização de acentos via unaccent do PostgreSQL).
        Complementa o Qdrant para queries com nomes específicos não surfaçados pelo vetor.
        """
        import re
        import unicodedata
        from sqlalchemy import select as sa_select, or_, func
        from app.models.chunk import Chunk
        from app.models.documento import Documento

        _STOPWORDS = {
            'para', 'como', 'qual', 'quem', 'onde', 'quando', 'algum', 'existe',
            'consta', 'autos', 'nome', 'chamado', 'alguma', 'pessoa', 'disse',
            'suas', 'seus', 'este', 'esta', 'esse', 'essa', 'pelo', 'pela',
            'sobre', 'falar', 'fala', 'falou', 'dizer', 'fazer',
        }

        def _strip_accents(s: str) -> str:
            return ''.join(
                c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn'
            )

        # Extrair nomes próprios capitalizados primeiro
        palavras = re.findall(r'\b[A-ZÀ-Úa-zà-ú][a-zà-ú]{2,}\b', query)
        # Filtrar stopwords e palavras curtas
        palavras = [w for w in palavras if _strip_accents(w.lower()) not in _STOPWORDS and len(w) >= 4]

        if not palavras:
            return []

        # Usar unaccent do PostgreSQL para match robusto (ignora acentos em ambos os lados)
        # Ex: query "flavio" → bate com "Flávio" no banco
        palavras_norm = [_strip_accents(p.lower()) for p in palavras[:5]]
        filtros_unaccent = [
            func.unaccent(func.lower(Chunk.texto)).ilike(f"%{pn}%")
            for pn in palavras_norm
        ]
        filtros_plain = [Chunk.texto.ilike(f"%{p}%") for p in palavras[:5]]

        try:
            result = await db.execute(
                sa_select(Chunk)
                .where(
                    Chunk.inquerito_id == uuid.UUID(inquerito_id),
                    or_(*filtros_unaccent),
                )
                .order_by(Chunk.pagina_inicial)
                .limit(limit)
            )
        except Exception:
            # fallback sem unaccent caso extensão não esteja instalada
            logger.warning("[COPILOTO] unaccent não disponível, usando ILIKE simples")
            result = await db.execute(
                sa_select(Chunk)
                .where(
                    Chunk.inquerito_id == uuid.UUID(inquerito_id),
                    or_(*filtros_plain),
                )
                .order_by(Chunk.pagina_inicial)
                .limit(limit)
            )
        chunks = result.scalars().all()

        # Buscar nomes dos documentos
        doc_ids = list({str(c.documento_id) for c in chunks})
        doc_nomes = {}
        if doc_ids:
            docs_result = await db.execute(
                sa_select(Documento).where(Documento.id.in_([uuid.UUID(d) for d in doc_ids]))
            )
            for doc in docs_result.scalars().all():
                doc_nomes[str(doc.id)] = doc.nome_arquivo or str(doc.id)

        return [
            {
                "score": 0.75,  # score fixo para resultados textuais
                "payload": {
                    "chunk_id": str(c.id),
                    "texto_preview": c.texto[:2000],
                    "documento_id": doc_nomes.get(str(c.documento_id), str(c.documento_id)),
                    "pagina_inicial": c.pagina_inicial,
                    "pagina_final": c.pagina_final,
                    "tipo_documento": c.tipo_documento or "não classificado",
                    "fonte": "busca_textual",
                },
            }
            for c in chunks
        ]

    async def _auditar_resposta(
        self,
        resposta: str,
        contexto_rag: str,
    ) -> Dict[str, Any]:
        """
        Auditoria factual obrigatória (blueprint §8).
        Usa modelo econômico para verificar citações, distorções e extrapolações.
        """
        logger.info("[COPILOTO] Executando auditoria factual")

        prompt_auditoria = SYSTEM_PROMPT_AUDITORIA_FACTUAL.format(
            resposta=resposta,
            contexto_rag=contexto_rag,
        )

        result = await self.llm_service.chat_completion(
            messages=[
                {"role": "system", "content": "Você é um auditor factual. Responda em JSON."},
                {"role": "user", "content": prompt_auditoria},
            ],
            tier="auditoria",
            temperature=0.1,
            agente="AuditoriaFactual",
            max_tokens=1000,
            json_mode=True,
        )

        # Tentar parsear JSON
        import json
        try:
            auditoria = json.loads(result["content"])
        except json.JSONDecodeError:
            auditoria = {
                "status": "erro",
                "score_confiabilidade": None,
                "raw": result["content"][:500],
            }

        auditoria["modelo_auditor"] = result["model"]
        auditoria["custo_auditoria"] = result["custo_estimado"]

        logger.info(
            f"[COPILOTO] Auditoria: {auditoria.get('status', 'N/A')} — "
            f"confiabilidade: {auditoria.get('score_confiabilidade', 'N/A')}"
        )

        return auditoria
