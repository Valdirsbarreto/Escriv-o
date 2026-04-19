"""
Escrivão AI — Serviço Copiloto Investigativo
RAG pipeline: query → embed → Qdrant → contexto → LLM → resposta com citações.
Conforme blueprint §7.3 e especificação §5.
"""

import json
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
        texto_anexo: Optional[str] = None,  # texto extraído de arquivo anexado pelo usuário
        nome_anexo: Optional[str] = None,   # nome original do arquivo
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

        # Injetar índice das peças dos autos (tabela de conteúdo do inquérito)
        # Permite ao LLM saber o que existe nos autos sem busca vetorial,
        # especialmente útil quando o Comissário menciona peças pelo tipo ou andamento processual.
        if db is not None:
            try:
                from sqlalchemy import select as sa_select  # noqa: F811
                from app.models.documento import Documento

                docs_result = await db.execute(
                    sa_select(Documento.nome_arquivo, Documento.tipo_peca, Documento.total_paginas)
                    .where(Documento.inquerito_id == uuid.UUID(inquerito_id))
                    .where(Documento.status_processamento == "concluido")
                    .order_by(Documento.tipo_peca, Documento.nome_arquivo)
                )
                docs_autos = docs_result.all()

                if docs_autos:
                    bloco_idx = ["### Índice das Peças dos Autos (documentos indexados)\n"]
                    for nome, tipo, total_pgs in docs_autos:
                        tipo_label = tipo or "outro"
                        pgs_label = f" ({total_pgs} pgs)" if total_pgs else ""
                        bloco_idx.append(f"- [{tipo_label.upper()}] {nome}{pgs_label}")
                    bloco_idx.append("\n---")
                    contexto_partes.append("\n".join(bloco_idx))
                    logger.info(f"[COPILOTO] Índice de peças injetado: {len(docs_autos)} documentos")
            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao buscar índice de peças: {e}")

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
                            # Incluir ID para que o Copiloto possa acionar OSINT Web por pessoa
                            bloco.append(f"- {p.nome}{papel}{cpf}{obs} [id:{p.id}]")

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
                    bloco_docs = ["### Documentos Gerados pela IA\n"]
                    # Docs estruturais (relatório inicial e síntese) são injetados completos —
                    # o LLM precisa do conteúdo integral para responder sobre suspeitos, conduta, etc.
                    # Demais docs (ofícios, minutas) ficam truncados em 3000 chars.
                    # relatorio_inicial é injetado completo — é a fonte de verdade do caso.
                    # sintese_investigativa fica truncada: foi gerada com contexto anterior
                    # e pode estar obsoleta se o relatório inicial foi regenerado.
                    TIPOS_COMPLETOS = {"relatorio_inicial"}
                    for dg in docs_gerados:
                        data = dg.created_at.strftime("%d/%m/%Y") if dg.created_at else ""
                        limite = len(dg.conteudo) if dg.tipo in TIPOS_COMPLETOS else 3000
                        bloco_docs.append(f"**[{dg.tipo.upper()}] {dg.titulo}** ({data})\n{dg.conteudo[:limite]}")
                        bloco_docs.append("---")
                    contexto_partes.insert(0, "\n".join(bloco_docs))
                    logger.info(f"[COPILOTO] {len(docs_gerados)} doc(s) gerado(s) injetado(s) no contexto")
            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao buscar docs gerados: {e}")

        # Injetar resultados dos agentes de inteligência (Sherlock, OSINT, fichas)
        # São o núcleo da análise investigativa — Copiloto é o centro de comando
        if db is not None:
            try:
                from sqlalchemy import select as sa_select  # noqa: F811
                from app.models.resultado_agente import ResultadoAgente

                agentes_res = await db.execute(
                    sa_select(ResultadoAgente)
                    .where(ResultadoAgente.inquerito_id == uuid.UUID(inquerito_id))
                    .order_by(ResultadoAgente.created_at.desc())
                )
                todos_agentes = agentes_res.scalars().all()

                # ── Sherlock (análise estratégica de 5 camadas) ──────────────
                sherlock_rec = next(
                    (r for r in todos_agentes if r.tipo_agente == "sherlock"), None
                )
                if sherlock_rec:
                    d = sherlock_rec.resultado_json or {}
                    bloco_sh = ["### Análise Sherlock — Estratégia Investigativa\n"]
                    if d.get("resumo_executivo"):
                        bloco_sh.append(f"**Resumo:** {d['resumo_executivo'][:600]}")
                    if d.get("tese_autoria"):
                        bloco_sh.append(f"**Tese de Autoria:** {d['tese_autoria'][:500]}")
                    if d.get("crimes_identificados"):
                        crimes_str = ", ".join(str(c) for c in d["crimes_identificados"][:5])
                        bloco_sh.append(f"**Crimes identificados:** {crimes_str}")
                    if d.get("contradicoes"):
                        bloco_sh.append(f"**Contradições:** {len(d['contradicoes'])} identificadas")
                    if d.get("backlog_diligencias"):
                        bloco_sh.append(f"**Diligências prioritárias:** {len(d['backlog_diligencias'])} pendentes")
                    if d.get("vulnerabilidades_defesa"):
                        bloco_sh.append(f"**Vulnerabilidades da defesa:** {len(d['vulnerabilidades_defesa'])} mapeadas")
                    if d.get("recomendacao_final"):
                        bloco_sh.append(f"**Recomendação:** {d['recomendacao_final'][:300]}")
                    bloco_sh.append("\n---")
                    contexto_partes.append("\n".join(bloco_sh))
                    logger.info("[COPILOTO] Análise Sherlock injetada no contexto")

                # ── OSINT, fichas, análises preliminares ─────────────────────
                fichas = [r for r in todos_agentes if r.tipo_agente in ("ficha_pessoa", "ficha_empresa")]
                osint_web = [r for r in todos_agentes if r.tipo_agente == "osint_web_pessoa"]
                osint_grat = [r for r in todos_agentes if r.tipo_agente == "osint_gratuito"]
                analises_prel = [r for r in todos_agentes if r.tipo_agente in ("analise_preliminar_pessoa", "analise_preliminar_empresa")]

                bloco_intel = []
                vistos = set()

                for r in fichas[:6]:
                    ref = str(r.referencia_id)
                    if ref in vistos:
                        continue
                    vistos.add(ref)
                    d = r.resultado_json or {}
                    if d.get("nivel_risco") or d.get("alertas"):
                        alertas_str = json.dumps((d.get("alertas") or [])[:3], ensure_ascii=False)
                        bloco_intel.append(
                            f"[FICHA {r.tipo_agente.replace('ficha_', '').upper()}] "
                            f"Risco: {d.get('nivel_risco', '?')} | Alertas: {alertas_str}"
                        )

                for r in analises_prel[:4]:
                    ref = str(r.referencia_id)
                    if ref in vistos:
                        continue
                    vistos.add(ref)
                    d = r.resultado_json or {}
                    if d.get("nivel_risco") or d.get("alertas"):
                        alertas_str = json.dumps((d.get("alertas") or [])[:3], ensure_ascii=False)
                        bloco_intel.append(
                            f"[ANÁLISE PRELIMINAR] Risco: {d.get('nivel_risco', '?')} | "
                            f"Alertas: {alertas_str}"
                        )

                for r in osint_web[:3]:
                    d = r.resultado_json or {}
                    alertas = (d.get("alertas") or [])[:2]
                    juridicas = (d.get("mencoes_juridicas") or [])[:2]
                    if alertas or juridicas:
                        bloco_intel.append(
                            f"[OSINT WEB] Presença: {d.get('presenca_digital', '?')} | "
                            f"Alertas: {json.dumps(alertas, ensure_ascii=False)} | "
                            f"Jurídico: {json.dumps(juridicas, ensure_ascii=False)}"
                        )

                for r in osint_grat[:3]:
                    d = r.resultado_json or {}
                    alertas = (d.get("alertas") or [])[:2]
                    if alertas or d.get("situacao_cadastral"):
                        bloco_intel.append(
                            f"[OSINT RECEITA FEDERAL] Situação: {d.get('situacao_cadastral', '?')} | "
                            f"Alertas: {json.dumps(alertas, ensure_ascii=False)}"
                        )

                if bloco_intel:
                    contexto_partes.append(
                        "### Inteligência sobre Personagens (OSINT + Fichas)\n\n"
                        + "\n".join(bloco_intel)
                        + "\n\n---"
                    )
                    logger.info(f"[COPILOTO] {len(bloco_intel)} entradas de inteligência injetadas")

            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao injetar resultados de agentes: {e}")

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

        # ── 2b. Few-shot: casos históricos similares (Banco de Casos Gold) ───
        try:
            from app.services.casos_gold_service import CasosGoldService
            casos = await CasosGoldService().buscar_casos_similares(query=query, top_k=2)
            if casos:
                casos_ctx = "\n\n### Casos Históricos Similares (referência investigativa)\n"
                for c in casos:
                    casos_ctx += f"\n**{c['titulo']}** ({c['tipo']}):\n{c['texto'][:800]}\n---\n"
                # Prepend ao contexto
                contexto_rag = casos_ctx + contexto_rag
        except Exception:
            pass  # few-shot é complementar, nunca bloqueia

        # ── 3. Montar mensagens ───────────────────────────
        system_prompt = SYSTEM_PROMPT_COPILOTO.format(
            numero_inquerito=numero_inquerito,
            estado_atual=estado_atual,
            total_paginas=total_paginas,
            total_documentos=total_documentos,
            contexto_rag=contexto_rag,
        )

        # ── Instruções de ferramentas disponíveis ─────────────────────────────
        tool_instruction = (
            "FERRAMENTAS DISPONÍVEIS — você é o centro de comando investigativo do Comissário:\n\n"

            "1. OSINT DirectData (dados cadastrais externos — CPF, CNPJ, placa, nome):\n"
            "   Use quando precisar de dados NÃO constantes nos autos.\n"
            "   Resposta EXCLUSIVAMENTE: <OSINT_CALL>{\"cpf\": \"123.456.789-00\"}</OSINT_CALL>\n"
            "   Variantes: {\"cnpj\": \"...\"} | {\"placa\": \"ABC1234\"} | {\"nome\": \"...\"}\n\n"

            "2. Agente Sherlock (análise estratégica em 5 camadas — contradições, tese de autoria, diligências, advogado do diabo):\n"
            "   Use quando o Comissário pedir análise estratégica do caso, tese de autoria, ou 'quais são as fraquezas da investigação'.\n"
            "   Resposta EXCLUSIVAMENTE: <SHERLOCK_CALL>{}</SHERLOCK_CALL>\n\n"

            "3. OSINT Web — fontes abertas (Google, JusBrasil, Escavador, DOU, notícias) para UMA pessoa:\n"
            "   Use quando precisar de menções públicas sobre um personagem. Informe o ID da pessoa.\n"
            "   Resposta EXCLUSIVAMENTE: <OSINT_WEB_CALL>{\"pessoa_id\": \"uuid-da-pessoa\"}</OSINT_WEB_CALL>\n"
            "   (Os IDs estão no índice de pessoas acima, no campo [id:...])\n\n"

            "4. Blockchain/Cripto (Chainabuse + Etherscan):\n"
            "   Use ao detectar endereços de carteiras (0x...) em investigações de lavagem.\n"
            "   Resposta EXCLUSIVAMENTE: <CRIPTO_CALL>{\"address\": \"0x...\"}</CRIPTO_CALL>\n\n"

            "5. Busca Global — pesquisa nome, apelido ou CPF em TODOS os inquéritos do sistema:\n"
            "   Use quando o Comissário perguntar se uma pessoa aparece em outros inquéritos, ou quando\n"
            "   buscar alguém sem saber em qual IP está (ex: 'tem algum inquérito sobre o Peixão?').\n"
            "   Resposta EXCLUSIVAMENTE: <BUSCA_GLOBAL_CALL>{\"termo\": \"nome ou CPF\"}</BUSCA_GLOBAL_CALL>\n\n"

            "REGRA OBRIGATÓRIA: Se usar qualquer ferramenta acima, sua resposta deve conter SOMENTE a tag XML, "
            "sem texto antes ou depois. O sistema executará, devolverá os dados e você analisará na rodada seguinte."
        )
        system_prompt += f"\n\n{tool_instruction}"
        
        messages = [{"role": "system", "content": system_prompt}]

        # Incluir histórico (últimas N mensagens para caber no contexto)
        if historico:
            ultimas = historico[-20:]
            messages.extend(ultimas)

        # Se há anexo, injeta como bloco no início do conteúdo do usuário
        if texto_anexo:
            nome_label = f' ("{nome_anexo}")' if nome_anexo else ""
            user_content = (
                f"[DOCUMENTO ANEXADO{nome_label}]\n"
                f"{texto_anexo[:30000]}\n"
                f"[FIM DO DOCUMENTO ANEXADO]\n\n"
                f"{query}"
            )
        else:
            user_content = query

        messages.append({"role": "user", "content": user_content})

        # ── 4. Chamar LLM (Loop Agentico) ────────────────────────────────
        logger.info("[COPILOTO] Enviando para LLM (standard)")

        resultado_osint_texto = ""
        try:
            llm_result = await self.llm_service.chat_completion(
                messages=messages,
                tier="premium",
                temperature=0.3,
                max_tokens=8000,
                agente="Copiloto",
            )
            resposta = llm_result["content"]
            
            # Loop de Tool Calling (OSINT)
            import re, json
            if "<OSINT_CALL>" in resposta:
                match = re.search(r"<OSINT_CALL>(.*?)</OSINT_CALL>", resposta, re.DOTALL)
                if match:
                    try:
                        args = json.loads(match.group(1).strip())
                        logger.info(f"[COPILOTO] Acionando Ferramenta OSINT com: {args}")
                        from app.services.osint_service import OsintService
                        osrm = OsintService()
                        res_osint = await osrm.consulta_avulsa(**args)
                        resultado_osint_texto = json.dumps(res_osint, ensure_ascii=False, indent=2)
                        
                        # Realimentar o LLM com os dados externos
                        messages.append({"role": "model", "content": resposta})
                        messages.append({
                            "role": "user", 
                            "content": f"[RETORNO DA FERRAMENTA OSINT]\n{resultado_osint_texto[:15000]}\n[FIM DO RETORNO]\n"
                                       f"Analise os dados acima e responda de forma elegante ao Comissário."
                        })
                        
                        logger.info("[COPILOTO] Enviando resultado OSINT de volta para o LLM")
                        llm_result2 = await self.llm_service.chat_completion(
                            messages=messages,
                            tier="premium",
                            temperature=0.4,
                            max_tokens=3000,
                            agente="Copiloto",
                        )
                        resposta = llm_result2["content"]
                        llm_result["tokens_prompt"] += llm_result2["tokens_prompt"]
                        llm_result["tokens_resposta"] += llm_result2["tokens_resposta"]
                        llm_result["custo_estimado"] += llm_result2["custo_estimado"]
                    except Exception as json_e:
                        logger.error(f"[COPILOTO] Erro ao parsear Tool OSINT: {json_e}")
            
            if "<CRIPTO_CALL>" in resposta:
                match = re.search(r"<CRIPTO_CALL>(.*?)</CRIPTO_CALL>", resposta, re.DOTALL)
                if match:
                    try:
                        args = json.loads(match.group(1).strip())
                        logger.info(f"[COPILOTO] Acionando Ferramenta CRIPTO com: {args}")
                        from app.services.cripto_service import CriptoService
                        cripto = CriptoService()
                        res_cripto = await cripto.analisar_carteira_completa(args.get("address"))
                        res_str = json.dumps(res_cripto, ensure_ascii=False, indent=2)

                        # Injetar o prompt especializado para a análise final
                        from app.core.prompts import SYSTEM_PROMPT_CRIPTO
                        messages.append({"role": "model", "content": resposta})
                        messages.append({
                            "role": "user",
                            "content": f"{SYSTEM_PROMPT_CRIPTO}\n\n[DADOS BRUTOS DA BLOCKCHAIN]\n{res_str[:15000]}\n"
                                       f"Analise os dados e gere o relatório final do Comissário IA."
                        })

                        llm_result2 = await self.llm_service.chat_completion(
                            messages=messages,
                            tier="premium",
                            temperature=0.2, # Menos criatividade, mais análise
                            max_tokens=3000,
                            agente="AgenteCripto",
                        )
                        resposta = llm_result2["content"]
                        llm_result["tokens_prompt"] += llm_result2["tokens_prompt"]
                        llm_result["tokens_resposta"] += llm_result2["tokens_resposta"]
                        llm_result["custo_estimado"] += llm_result2["custo_estimado"]
                    except Exception as e:
                        logger.error(f"[COPILOTO] Erro na ferramenta Cripto: {e}")

            # ── Ferramenta Sherlock ────────────────────────────────────────────
            if "<SHERLOCK_CALL>" in resposta and db is not None:
                try:
                    logger.info("[COPILOTO] Acionando Agente Sherlock")
                    from app.services.sherlock_service import SherlockService
                    sherlock_svc = SherlockService()
                    analise = await sherlock_svc.gerar_estrategia(db, uuid.UUID(inquerito_id))
                    res_str = json.dumps(analise, ensure_ascii=False, indent=2)
                    messages.append({"role": "model", "content": resposta})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"[RETORNO DO AGENTE SHERLOCK — ANÁLISE ESTRATÉGICA EM 5 CAMADAS]\n"
                            f"{res_str[:12000]}\n[FIM DO RETORNO]\n\n"
                            "Com base nessa análise, responda ao Comissário de forma objetiva e acionável. "
                            "Destaque as contradições mais críticas, a tese de autoria principal e as "
                            "diligências mais urgentes."
                        ),
                    })
                    llm_result2 = await self.llm_service.chat_completion(
                        messages=messages,
                        tier="premium",
                        temperature=0.3,
                        max_tokens=4000,
                        agente="Copiloto",
                    )
                    resposta = llm_result2["content"]
                    llm_result["tokens_prompt"] += llm_result2["tokens_prompt"]
                    llm_result["tokens_resposta"] += llm_result2["tokens_resposta"]
                    llm_result["custo_estimado"] += llm_result2["custo_estimado"]
                    logger.info("[COPILOTO] Resposta Sherlock incorporada")
                except Exception as e:
                    logger.error(f"[COPILOTO] Erro ao acionar Sherlock: {e}")

            # ── Ferramenta OSINT Web ───────────────────────────────────────────
            if "<OSINT_WEB_CALL>" in resposta and db is not None:
                match = re.search(r"<OSINT_WEB_CALL>(.*?)</OSINT_WEB_CALL>", resposta, re.DOTALL)
                if match:
                    try:
                        args = json.loads(match.group(1).strip())
                        pessoa_id_str = args.get("pessoa_id", "")
                        logger.info(f"[COPILOTO] Acionando OSINT Web para pessoa {pessoa_id_str}")
                        from app.services.agente_ficha import AgenteFicha
                        ficha_svc = AgenteFicha()
                        res_osint_web = await ficha_svc.gerar_osint_web_pessoa(
                            db, uuid.UUID(inquerito_id), uuid.UUID(pessoa_id_str)
                        )
                        res_str = json.dumps(res_osint_web, ensure_ascii=False, indent=2)
                        messages.append({"role": "model", "content": resposta})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"[RETORNO OSINT WEB — FONTES ABERTAS (Google, JusBrasil, Escavador, DOU)]\n"
                                f"{res_str[:8000]}\n[FIM DO RETORNO]\n\n"
                                "Analise os resultados e responda ao Comissário destacando o que é mais "
                                "relevante para a investigação: alertas em notícias, menções jurídicas e "
                                "cruzamentos com os autos."
                            ),
                        })
                        llm_result2 = await self.llm_service.chat_completion(
                            messages=messages,
                            tier="premium",
                            temperature=0.3,
                            max_tokens=3000,
                            agente="Copiloto",
                        )
                        resposta = llm_result2["content"]
                        llm_result["tokens_prompt"] += llm_result2["tokens_prompt"]
                        llm_result["tokens_resposta"] += llm_result2["tokens_resposta"]
                        llm_result["custo_estimado"] += llm_result2["custo_estimado"]
                        logger.info("[COPILOTO] Resposta OSINT Web incorporada")
                    except Exception as e:
                        logger.error(f"[COPILOTO] Erro ao acionar OSINT Web: {e}")

            # ── Ferramenta Busca Global ────────────────────────────────────────
            if "<BUSCA_GLOBAL_CALL>" in resposta and db is not None:
                match = re.search(r"<BUSCA_GLOBAL_CALL>(.*?)</BUSCA_GLOBAL_CALL>", resposta, re.DOTALL)
                if match:
                    try:
                        args = json.loads(match.group(1).strip())
                        termo = args.get("termo", "")
                        logger.info(f"[COPILOTO] Acionando Busca Global para: '{termo}'")
                        resultados = await self._buscar_global(db, termo)
                        res_str = json.dumps(resultados, ensure_ascii=False, indent=2)
                        messages.append({"role": "model", "content": resposta})
                        if resultados:
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"[RETORNO DA BUSCA GLOBAL — '{termo}']\n"
                                    f"{res_str[:6000]}\n[FIM DO RETORNO]\n\n"
                                    "Com base nesses resultados, responda ao Comissário de forma natural. "
                                    "Indique em qual(is) inquérito(s) a pessoa aparece, seu papel e trechos relevantes. "
                                    "Se aparecer em múltiplos IPs, liste todos."
                                ),
                            })
                        else:
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"[RETORNO DA BUSCA GLOBAL]\nNenhum resultado encontrado para '{termo}' "
                                    "em nenhum inquérito do sistema.\n\n"
                                    "Informe ao Comissário que não há registros e sugira verificar o nome completo ou CPF."
                                ),
                            })
                        llm_result2 = await self.llm_service.chat_completion(
                            messages=messages,
                            tier="premium",
                            temperature=0.3,
                            max_tokens=2000,
                            agente="Copiloto",
                        )
                        resposta = llm_result2["content"]
                        llm_result["tokens_prompt"] += llm_result2["tokens_prompt"]
                        llm_result["tokens_resposta"] += llm_result2["tokens_resposta"]
                        llm_result["custo_estimado"] += llm_result2["custo_estimado"]
                        logger.info("[COPILOTO] Busca Global incorporada na resposta")
                    except Exception as e:
                        logger.error(f"[COPILOTO] Erro na Busca Global: {e}")

        except Exception as e:
            logger.error(f"[COPILOTO] LLM indisponível: {e}")
            return {
                "resposta": (
                    "⚠️ O serviço de LLM está temporariamente indisponível. "
                    "Por favor, verifique as configurações em .env e tente novamente.\n\n"
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
            # Palavras comuns que poluem a busca textual
            'temos', 'nosso', 'nossa', 'nossos', 'nossas', 'voce', 'você',
            'isso', 'aqui', 'mais', 'muito', 'pouco', 'algo', 'outra', 'outro',
            'pode', 'seria', 'seria', 'quer', 'sabe', 'saber', 'quero', 'queria',
            'fale', 'diga', 'diga', 'falar', 'fala', 'conte', 'conta',
            'informações', 'informacao', 'informacoes', 'dados', 'detalhes',
        }

        def _strip_accents(s: str) -> str:
            return ''.join(
                c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn'
            )

        # Preferência por NOMES PRÓPRIOS: palavras capitalizadas que não sejam
        # a primeira palavra da frase (mais prováveis de ser nomes de pessoas/lugares)
        tokens = re.findall(r'\S+', query)
        proprios = [
            w for w in re.findall(r'\b[A-ZÀ-Ú][a-zà-ú]{1,}\b', query)
            if _strip_accents(w.lower()) not in _STOPWORDS and len(w) >= 3
            and w != tokens[0]  # ignora primeira palavra da frase (pode ser maiúscula por padrão)
        ]

        # Fallback: qualquer palavra relevante com ≥4 chars
        todas = re.findall(r'\b[A-ZÀ-Úa-zà-ú][a-zà-ú]{2,}\b', query)
        comuns = [w for w in todas if _strip_accents(w.lower()) not in _STOPWORDS and len(w) >= 4]

        # Usar nomes próprios se existirem, caso contrário palavras comuns
        palavras = proprios if proprios else comuns

        if not palavras:
            return []

        # Nomes próprios buscam com AND (todos devem aparecer) se forem ≤ 2 termos
        # Caso contrário, OR — para não ser restritivo demais
        palavras_norm = [_strip_accents(p.lower()) for p in palavras[:4]]
        filtros_unaccent = [
            func.unaccent(func.lower(Chunk.texto)).ilike(f"%{pn}%")
            for pn in palavras_norm
        ]
        filtros_plain = [Chunk.texto.ilike(f"%{p}%") for p in palavras[:4]]

        # AND quando há 1-2 nomes próprios (busca focada); OR para 3+
        from sqlalchemy import and_ as sa_and
        combinar = sa_and if (proprios and len(palavras_norm) <= 2) else or_

        try:
            result = await db.execute(
                sa_select(Chunk)
                .where(
                    Chunk.inquerito_id == uuid.UUID(inquerito_id),
                    combinar(*filtros_unaccent),
                )
                .order_by(Chunk.pagina_inicial)
                .limit(limit)
            )
        except Exception:
            logger.warning("[COPILOTO] unaccent não disponível, usando ILIKE simples")
            result = await db.execute(
                sa_select(Chunk)
                .where(
                    Chunk.inquerito_id == uuid.UUID(inquerito_id),
                    combinar(*filtros_plain),
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

    async def processar_mensagem_global(
        self,
        query: str,
        db,
        historico: list = None,
        resultados_precomputados: list = None,
    ) -> Dict[str, Any]:
        """
        Responde ao Comissário quando não há inquérito em contexto.
        Se resultados_precomputados vier preenchido, formata a resposta usando o LLM (natural).
        Caso contrário, o LLM decide chamar BUSCA_GLOBAL_CALL ele mesmo.
        """
        import re, json

        contexto_resultados = ""
        if resultados_precomputados:
            linhas = ["### Resultados da busca nos inquéritos do sistema\n"]
            for r in resultados_precomputados:
                desc = f" — {r['descricao'][:60]}" if r.get("descricao") else ""
                mencoes = ("\n  Menções: " + " | ".join(r["mencoes"][:3])) if r.get("mencoes") else ""
                linhas.append(f"- **{r['numero']}** (id:`{r['inquerito_id']}`){desc}{mencoes}")
            contexto_resultados = "\n".join(linhas)

        system_prompt = (
            "Você é o Copiloto Investigativo do Comissário da Polícia Civil. "
            "Nenhum inquérito específico está em foco agora.\n\n"
            + (contexto_resultados + "\n\n" if contexto_resultados else "")
            + "FERRAMENTA DISPONÍVEL:\n"
            "- Busca Global: <BUSCA_GLOBAL_CALL>{\"termo\": \"nome ou CPF\"}</BUSCA_GLOBAL_CALL>\n"
            "  Use quando precisar pesquisar alguém sem saber o número do IP.\n\n"
            "Responda de forma natural e direta ao Comissário. "
            "Se encontrou a pessoa em múltiplos IPs, liste todos com o que há de relevante. "
            "Se apenas um IP, diga o número e o que foi encontrado. "
            "Nunca anuncie que 'o contexto foi carregado'. "
            "Nunca use 'Doutor' — o tratamento correto é 'Comissário'."
        )

        messages = [{"role": "system", "content": system_prompt}]
        if historico:
            messages.extend(historico[-10:])
        messages.append({"role": "user", "content": query})

        llm_result = await self.llm_service.chat_completion(
            messages=messages,
            tier="premium",
            temperature=0.3,
            max_tokens=1500,
            agente="CopilotoGlobal",
        )
        resposta = llm_result["content"]

        # Se o LLM decidiu fazer a busca global (sem resultados precomputados)
        if "<BUSCA_GLOBAL_CALL>" in resposta and db is not None and not resultados_precomputados:
            match = re.search(r"<BUSCA_GLOBAL_CALL>(.*?)</BUSCA_GLOBAL_CALL>", resposta, re.DOTALL)
            if match:
                try:
                    args = json.loads(match.group(1).strip())
                    termo = args.get("termo", query)
                    resultados = await self._buscar_global(db, termo)
                    res_str = json.dumps(resultados, ensure_ascii=False, indent=2)
                    messages.append({"role": "model", "content": resposta})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"[RETORNO DA BUSCA GLOBAL]\n{res_str[:5000]}\n[FIM]\n\n"
                            "Responda ao Comissário de forma natural indicando onde a pessoa aparece."
                        ),
                    })
                    llm_result2 = await self.llm_service.chat_completion(
                        messages=messages, tier="premium", temperature=0.3,
                        max_tokens=1500, agente="CopilotoGlobal",
                    )
                    resposta = llm_result2["content"]
                except Exception as e:
                    logger.error(f"[COPILOTO-GLOBAL] Erro na ferramenta: {e}")

        return {"resposta": resposta, "fontes": [], "modelo": llm_result.get("model", "")}

    async def _buscar_global(self, db, termo: str) -> list:
        """
        Pesquisa nome, apelido ou CPF em TODOS os inquéritos do sistema.
        Retorna lista de dicts {inquerito_id, numero, descricao, mencoes[]}.
        Usada pelo handler de <BUSCA_GLOBAL_CALL>.
        """
        import re as _re
        import unicodedata
        from sqlalchemy import select as sa_select, func as sa_func, or_
        from sqlalchemy import and_ as sa_and
        from app.models.pessoa import Pessoa
        from app.models.chunk import Chunk
        from app.models.inquerito import Inquerito

        _SW = {
            'que', 'tem', 'sobre', 'para', 'como', 'qual', 'quem', 'algum', 'alguma',
            'sabe', 'saber', 'existe', 'existir', 'ver', 'veja', 'voce', 'você',
            'sim', 'não', 'nao', 'este', 'esse', 'isso', 'aqui', 'ali',
            'lembro', 'acho', 'inquerito', 'policial', 'nacional', 'conhecido',
            'apelido', 'alcunha', 'nome', 'pessoa', 'tem',
        }

        def strip_acc(s: str) -> str:
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

        # Extrair termos: CPF + nomes próprios
        termos = []
        for c in _re.findall(r'\d{3}[\.\-]?\d{3}[\.\-]?\d{3}[\-\.]?\d{2}', termo):
            termos.append(_re.sub(r'[\.\-]', '', c))

        # Quoted strings first (highest priority)
        for q in _re.findall(r'["\']([^"\']{3,})["\']', termo):
            termos.append(q)

        tokens = termo.split()
        for i, tok in enumerate(tokens):
            palavra = _re.sub(r'[^\w]', '', tok)
            if len(palavra) < 3 or strip_acc(palavra.lower()) in _SW:
                continue
            # Capitalizada (não a primeira palavra) → provável nome próprio
            if palavra[0].isupper() and i > 0:
                termos.append(palavra)
            # Qualquer palavra ≥ 4 chars como fallback
            elif len(palavra) >= 4:
                termos.append(palavra)

        termos_norm = list({strip_acc(t.lower()) for t in termos if len(t) >= 3})
        if not termos_norm:
            # fallback: usa todas as palavras ≥ 4 chars sem stopword
            termos_norm = [
                strip_acc(w.lower()) for w in termo.split()
                if len(w) >= 4 and strip_acc(w.lower()) not in _SW
            ]
        if not termos_norm:
            return []

        logger.info(f"[BUSCA-GLOBAL] Termos normalizados: {termos_norm}")

        # ── Busca Pessoa ──────────────────────────────────────────────────────
        filtros_p = [sa_func.unaccent(sa_func.lower(Pessoa.nome)).ilike(f"%{t}%") for t in termos_norm[:4]]
        filtros_p += [sa_func.unaccent(sa_func.lower(Pessoa.observacoes)).ilike(f"%{t}%") for t in termos_norm[:2]]
        filtros_p += [Pessoa.cpf.ilike(f"%{t}%") for t in termos_norm if t.isdigit()]
        try:
            rp = await db.execute(
                sa_select(Pessoa.inquerito_id, Pessoa.nome, Pessoa.tipo_pessoa)
                .where(or_(*filtros_p))
                .limit(25)
            )
            rows_p = rp.all()
        except Exception:
            rows_p = []

        # ── Busca Chunk ───────────────────────────────────────────────────────
        filtros_c = [sa_func.unaccent(sa_func.lower(Chunk.texto)).ilike(f"%{t}%") for t in termos_norm[:3]]
        try:
            combinar = sa_and if len(filtros_c) <= 2 else or_
            rc = await db.execute(
                sa_select(Chunk.inquerito_id, Chunk.texto)
                .where(combinar(*filtros_c))
                .limit(30)
            )
            rows_c = rc.all()
        except Exception:
            rows_c = []

        # ── Agrupar por inquérito ─────────────────────────────────────────────
        por_inq: dict = {}
        for row in rows_p:
            iid = str(row.inquerito_id)
            por_inq.setdefault(iid, {"mencoes": set()})
            por_inq[iid]["mencoes"].add(f"{row.nome} [{row.tipo_pessoa or 'pessoa'}]")

        for row in rows_c:
            iid = str(row.inquerito_id)
            por_inq.setdefault(iid, {"mencoes": set()})
            texto = row.texto
            for t in termos_norm:
                idx = strip_acc(texto.lower()).find(t)
                if idx >= 0:
                    ini = max(0, idx - 40)
                    fim = min(len(texto), idx + len(t) + 60)
                    por_inq[iid]["mencoes"].add(f"…{texto[ini:fim].strip()}…")
                    break

        if not por_inq:
            return []

        ids = [uuid.UUID(i) for i in por_inq.keys()]
        res_inq = await db.execute(
            sa_select(Inquerito.id, Inquerito.numero, Inquerito.descricao)
            .where(Inquerito.id.in_(ids))
            .order_by(Inquerito.updated_at.desc())
        )
        resultado = []
        for inq in res_inq.all():
            iid = str(inq.id)
            resultado.append({
                "inquerito_id": iid,
                "numero": inq.numero,
                "descricao": inq.descricao or "",
                "mencoes": list(por_inq[iid]["mencoes"])[:4],
            })

        logger.info(f"[BUSCA-GLOBAL] {len(resultado)} inquérito(s) com resultados")
        return resultado

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
