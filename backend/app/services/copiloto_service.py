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
        max_chunks: int = 8,
        auditar: bool = True,
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
        logger.info("[COPILOTO] Enviando para LLM (premium)")

        try:
            llm_result = await self.llm_service.chat_completion(
                messages=messages,
                tier="premium",
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
