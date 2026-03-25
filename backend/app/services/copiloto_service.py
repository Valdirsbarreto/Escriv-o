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

# ── Detecção de intenção de geração ──────────────────────────────────────────

_INTENT_GERAR: list[tuple[list[str], str]] = [
    (["despacho saneador", "despacho sanead"], "despacho_saneador"),
    (["relatório final", "relatorio final"], "relatorio_final"),
    (["relatório parcial", "relatorio parcial"], "relatorio_parcial"),
    (["ofício de requisição", "oficio de requisicao", "ofício requisição"], "oficio_requisicao"),
    (["busca e apreensão", "busca e apreensao", "mandado de busca"], "mandado_busca"),
    (["interceptação", "interceptacao"], "interceptacao_telefonica"),
    (["sigilo bancário", "sigilo bancario", "quebra de sigilo"], "quebra_sigilo_bancario"),
    (["prisão preventiva", "prisao preventiva"], "autorizacao_prisao"),
    (["despacho"], "despacho_generico"),
    (["ofício", "oficio"], "oficio_generico"),
    (["relatório", "relatorio"], "relatorio_final"),
]

_VERBOS_GERAR = [
    "faça", "faz", "elabore", "elabora", "redija", "redige",
    "gere", "gera", "produza", "produz", "crie", "cria",
    "escreva", "escreve", "prepare", "prepara", "minutar", "minuta",
]

_PALAVRAS_APROVACAO = [
    "aprovado", "aprovar", "aprovei", "finalizar", "finalizado",
    "ok finalizar", "salvar", "aceito", "perfeito, finalizar",
]


def _detectar_intencao_gerar(query: str) -> str | None:
    q = query.lower().strip()
    tem_verbo = any(v in q for v in _VERBOS_GERAR)
    if not tem_verbo:
        return None
    for keywords, tipo in _INTENT_GERAR:
        if any(kw in q for kw in keywords):
            return tipo
    return None


def _eh_aprovacao(query: str) -> bool:
    q = query.lower().strip()
    return any(p in q for p in _PALAVRAS_APROVACAO)


# ── Armazenamento de rascunho em Redis ───────────────────────────────────────

async def _redis_client():
    import redis.asyncio as aioredis
    from app.core.config import settings
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _salvar_rascunho(sessao_id: str, dados: dict):
    r = await _redis_client()
    import json
    await r.set(f"copiloto:draft:{sessao_id}", json.dumps(dados, ensure_ascii=False), ex=86400)
    await r.aclose()


async def _obter_rascunho(sessao_id: str) -> dict | None:
    r = await _redis_client()
    import json
    raw = await r.get(f"copiloto:draft:{sessao_id}")
    await r.aclose()
    return json.loads(raw) if raw else None


async def _limpar_rascunho(sessao_id: str):
    r = await _redis_client()
    await r.delete(f"copiloto:draft:{sessao_id}")
    await r.aclose()


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
        sessao_id: str = "",
        historico: List[Dict[str, str]] = None,
        numero_inquerito: str = "",
        estado_atual: str = "",
        total_paginas: int = 0,
        total_documentos: int = 0,
        max_chunks: int = 8,
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

        # ── 0. Modo editor de documentos ──────────────────
        if sessao_id:
            draft = await _obter_rascunho(sessao_id)
            if draft:
                if _eh_aprovacao(query):
                    return await self._aprovar_documento(draft, inquerito_id, sessao_id, numero_inquerito, db, t_total)
                else:
                    return await self._editar_documento(draft, query, inquerito_id, sessao_id, numero_inquerito, db, t_total)

            tipo = _detectar_intencao_gerar(query)
            if tipo:
                return await self._gerar_documento(tipo, query, inquerito_id, sessao_id, numero_inquerito, db, t_total)

        # ── 1. Busca RAG ──────────────────────────────────
        logger.info(f"[COPILOTO] Buscando contexto para: {query[:80]}...")

        query_vector = self.embedding_service.generate(query)

        resultados = self.qdrant_service.search(
            query_vector=query_vector,
            limit=max_chunks,
            inquerito_id=inquerito_id,
        )

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
            "Nenhum trecho relevante encontrado nos autos indexados. "
            "Informe ao delegado que a informação solicitada pode não constar nos documentos disponíveis."
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
        logger.info("[COPILOTO] Enviando para LLM (standard)")

        try:
            llm_result = await self.llm_service.chat_completion(
                messages=messages,
                tier="standard",
                temperature=0.3,
                max_tokens=3000,
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

    async def _obter_contexto_inquerito(self, inquerito_id: str, db) -> str:
        """Busca síntese/resumo do caso para contexto de geração."""
        contexto = ""
        if db is not None:
            try:
                from app.services.summary_service import SummaryService
                resumo = await SummaryService().obter_resumo_caso(db, uuid.UUID(inquerito_id))
                if resumo:
                    contexto = resumo[:6000]
            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao buscar resumo para geração: {e}")
        return contexto or "Contexto do inquérito não disponível."

    async def _gerar_documento(
        self, tipo: str, query: str, inquerito_id: str,
        sessao_id: str, numero_inquerito: str, db, t_total: float,
    ) -> Dict[str, Any]:
        from app.core.prompts import PROMPT_GERAR_DOCUMENTO
        from app.services.agente_cautelar import TIPOS_CAUTELAR

        titulo_tipo = TIPOS_CAUTELAR.get(tipo, tipo.replace("_", " ").title())
        contexto = await self._obter_contexto_inquerito(inquerito_id, db)

        prompt = PROMPT_GERAR_DOCUMENTO.format(
            tipo_documento=titulo_tipo,
            numero_inquerito=numero_inquerito,
            instrucoes=query,
            contexto=contexto,
            exemplos_estilo="",
        )

        result = await self.llm_service.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="premium",
            temperature=0.4,
            max_tokens=4000,
        )
        texto = result["content"].strip()

        draft = {"tipo": tipo, "titulo": titulo_tipo, "conteudo": texto, "versao": 1}
        await _salvar_rascunho(sessao_id, draft)
        logger.info(f"[COPILOTO] Rascunho '{titulo_tipo}' criado para sessão {sessao_id}")

        return {
            "resposta": texto,
            "fontes": [],
            "auditoria": None,
            "modo": "edicao_documento",
            "tipo_documento": tipo,
            "versao_rascunho": 1,
            "modelo": result["model"],
            "tokens_prompt": result["tokens_prompt"],
            "tokens_resposta": result["tokens_resposta"],
            "custo_estimado": result["custo_estimado"],
            "tempo_total_ms": int((time.time() - t_total) * 1000),
        }

    async def _editar_documento(
        self, draft: dict, instrucao: str, inquerito_id: str,
        sessao_id: str, numero_inquerito: str, db, t_total: float,
    ) -> Dict[str, Any]:
        from app.core.prompts import PROMPT_EDITAR_DOCUMENTO

        versao_atual = draft["versao"]
        contexto = await self._obter_contexto_inquerito(inquerito_id, db)

        prompt = PROMPT_EDITAR_DOCUMENTO.format(
            tipo_documento=draft["titulo"],
            versao=versao_atual,
            documento_atual=draft["conteudo"],
            instrucao=instrucao,
            contexto=contexto[:2000],
            proxima_versao=versao_atual + 1,
        )

        result = await self.llm_service.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="premium",
            temperature=0.3,
            max_tokens=4000,
        )
        texto = result["content"].strip()

        draft["conteudo"] = texto
        draft["versao"] = versao_atual + 1
        await _salvar_rascunho(sessao_id, draft)
        logger.info(f"[COPILOTO] Rascunho '{draft['titulo']}' atualizado para v{draft['versao']}")

        return {
            "resposta": texto,
            "fontes": [],
            "auditoria": None,
            "modo": "edicao_documento",
            "tipo_documento": draft["tipo"],
            "versao_rascunho": draft["versao"],
            "modelo": result["model"],
            "tokens_prompt": result["tokens_prompt"],
            "tokens_resposta": result["tokens_resposta"],
            "custo_estimado": result["custo_estimado"],
            "tempo_total_ms": int((time.time() - t_total) * 1000),
        }

    async def _aprovar_documento(
        self, draft: dict, inquerito_id: str,
        sessao_id: str, numero_inquerito: str, db, t_total: float,
    ) -> Dict[str, Any]:
        from app.models.resultado_agente import ResultadoAgente

        await _limpar_rascunho(sessao_id)

        if db is not None:
            try:
                registro = ResultadoAgente(
                    inquerito_id=uuid.UUID(inquerito_id),
                    tipo_agente="copiloto_editor",
                    resultado_json={"tipo": draft["tipo"], "versoes": draft["versao"]},
                    texto_gerado=draft["conteudo"],
                    modelo_llm="premium",
                )
                db.add(registro)
                await db.commit()
                logger.info(f"[COPILOTO] Documento '{draft['titulo']}' aprovado e salvo.")
            except Exception as e:
                logger.warning(f"[COPILOTO] Falha ao salvar documento aprovado: {e}")

        confirmacao = (
            f"✅ **{draft['titulo']}** aprovado e salvo nos autos do IP {numero_inquerito}.\n\n"
            f"O documento (versão {draft['versao']}) foi registrado no sistema. "
            f"Você pode copiá-lo acima ou acessá-lo em Cautelares."
        )

        return {
            "resposta": confirmacao,
            "fontes": [],
            "auditoria": None,
            "modo": "documento_aprovado",
            "tipo_documento": draft["tipo"],
            "modelo": "—",
            "tokens_prompt": 0,
            "tokens_resposta": 0,
            "custo_estimado": 0.0,
            "tempo_total_ms": int((time.time() - t_total) * 1000),
        }

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
            tier="economico",
            temperature=0.1,
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
