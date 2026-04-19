"""
Escrivão AI — Serviço LLM
Roteamento por tier:
  triagem/extracao/resumo/auditoria → Groq (Llama, OpenAI-compat)
  standard/vision                   → Gemini 1.5 Flash
  premium                           → Gemini 1.5 Pro

Registra automaticamente cada chamada em `consumo_api` (fire-and-forget).
"""

import asyncio
import logging
import time
import uuid
from decimal import Decimal
from typing import List, Dict, Optional, Any

from google import genai
from google.genai import types as genai_types

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Gerencia chamadas a LLMs com roteamento por tier.

    triagem    (llama-3.1-8b-instant)   : classificação de documentos — Groq
    extracao   (llama-3.3-70b-versatile): NER — Groq
    resumo     (llama-3.3-70b-versatile): resumos hierárquicos — Groq
    auditoria  (llama-3.3-70b-versatile): auditoria factual do copiloto — Groq
    standard   (gemini-1.5-flash)       : orquestração, extrato bancário, OCR
    premium    (gemini-1.5-pro)         : copiloto RAG, fichas, cautelares, síntese

    Parâmetro `agente`: nome do componente chamador para rastreio de custo.
    Exemplos: 'Copiloto', 'AgenteFicha', 'AgenteExtrato', 'Resumo', 'NER',
              'Classificacao', 'Orquestrador', 'AgenteCautelar'
    """

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY é obrigatório — todos os tiers agora usam Google Gemini"
            )
        self._genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.eco_model     = settings.LLM_ECONOMICO_MODEL    # gemini-1.5-flash-8b
        self.std_model     = settings.LLM_STANDARD_MODEL     # gemini-1.5-flash
        self.premium_model = settings.LLM_PREMIUM_MODEL      # gemini-1.5-pro

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tier: str = "premium",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        json_mode: bool = False,
        agente: str = "Desconhecido",
        thinking_budget: int = -1,
    ) -> Dict[str, Any]:
        """
        Envia mensagens para o LLM e retorna a resposta.

        Args:
            messages  : Lista de dicts com role e content
            tier      : "economico", "standard" ou "premium"
            temperature: 0.0 a 1.0 (mais baixo = mais preciso)
            max_tokens: máximo de tokens na resposta
            json_mode : se True, força resposta em JSON
            agente    : nome do componente chamador (para rastreio de custo)

        Returns:
            {content, model, tokens_prompt, tokens_resposta, custo_estimado, tempo_ms}
        """
        # ── Roteamento Integral Gemini ────────────────────────────────────────
        if tier in {"triagem", "extracao", "resumo", "auditoria", "economico"}:
            model = self.eco_model
            # Para o tier econômico (8b), usamos a temperatura do config se não informada
            if temperature == 0.3: # default do chat_completion
                temperature = settings.LLM_ECONOMICO_TEMPERATURE
        elif tier == "standard":
            model = self.std_model
        else:  # "premium"
            model = self.premium_model

        # Para tasks de geração longa (>= 8k tokens), desabilitar thinking por padrão
        # — thinking consome tokens do mesmo orçamento de max_output_tokens e trunca o texto.
        # Passa thinking_budget=0 explicitamente para desabilitar; -1 = decisão automática.
        effective_thinking = thinking_budget
        if effective_thinking == -1:
            effective_thinking = 0 if max_tokens >= 8000 else -1

        result = await self._gemini_completion(messages, model, temperature, max_tokens, json_mode, effective_thinking)

        # Registrar consumo (await direto pois roda sob asyncio.run no Celery)
        await self._registrar_consumo(
            agente=agente,
            tier=tier,
            model=model,
            tokens_prompt=result["tokens_prompt"],
            tokens_saida=result["tokens_resposta"],
            custo_usd=result["custo_estimado"],
            tempo_ms=result.get("tempo_ms"),
            status="ok",
        )

        return result

    async def _gemini_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        thinking_budget: int = -1,
    ) -> Dict[str, Any]:
        """Chamada para a API do Google Gemini."""
        t0 = time.time()
        try:
            gemini_messages = []
            system_instruction = None

            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                else:
                    role = "user" if msg["role"] == "user" else "model"
                    gemini_messages.append({"role": role, "parts": [{"text": msg["content"]}]})

            # thinking_budget=0 desabilita o raciocínio interno do Gemini 2.5.
            # Essencial para tasks de geração longa: thinking consome tokens do mesmo
            # orçamento de max_output_tokens e trunca a resposta antes de terminar.
            # ThinkingConfig foi adicionado no google-genai >= 1.5 — fallback defensivo.
            thinking_cfg = None
            if thinking_budget >= 0:
                try:
                    thinking_cfg = genai_types.ThinkingConfig(thinking_budget=thinking_budget)
                except AttributeError:
                    logger.warning("[LLM] ThinkingConfig não disponível nesta versão do SDK — ignorado")

            config = genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json" if json_mode else None,
                **({"thinking_config": thinking_cfg} if thinking_cfg is not None else {}),
            )

            # Timeout escala com max_tokens, mas limitado a 520s (abaixo do soft_time_limit das tasks)
            timeout_s = min(520, max(300, max_tokens // 60))
            response = await asyncio.wait_for(
                self._genai_client.aio.models.generate_content(
                    model=model,
                    contents=gemini_messages,
                    config=config,
                ),
                timeout=timeout_s,
            )

            tempo_ms = int((time.time() - t0) * 1000)

            content = response.text

            usage = getattr(response, "usage_metadata", None)
            tokens_prompt   = getattr(usage, "prompt_token_count", 0) or 0
            tokens_resposta = getattr(usage, "candidates_token_count", 0) or 0

            custo = self._estimar_custo(model, tokens_prompt, tokens_resposta)

            result = {
                "content": content,
                "model": model,
                "tokens_prompt": tokens_prompt,
                "tokens_resposta": tokens_resposta,
                "custo_estimado": custo,
                "tempo_ms": tempo_ms,
            }

            logger.info(
                f"[LLM-Gemini] {model} — {tokens_prompt}+{tokens_resposta} tokens, "
                f"{tempo_ms}ms, ~${custo:.4f}"
            )

            return result

        except asyncio.TimeoutError:
            tempo_ms = int((time.time() - t0) * 1000)
            logger.error(f"[LLM-Gemini] Timeout ({model}) após {tempo_ms}ms")
            # Registra o timeout na telemetria (fire-and-forget)
            asyncio.ensure_future(self._registrar_consumo(
                agente="timeout", tier="?", model=model,
                tokens_prompt=0, tokens_saida=0, custo_usd=0.0,
                tempo_ms=tempo_ms, status="timeout",
            ))
            raise
        except Exception as e:
            logger.error(f"[LLM-Gemini] Erro ({model}): {e}")
            raise


    async def _registrar_consumo(
        self,
        agente: str,
        tier: str,
        model: str,
        tokens_prompt: int,
        tokens_saida: int,
        custo_usd: float,
        tempo_ms: int = None,
        status: str = "ok",
    ) -> None:
        """Persiste o consumo no banco e dispara alerta Telegram se necessário."""
        try:
            from app.core.database import async_session
            from app.models.consumo_api import ConsumoApi
            from sqlalchemy import func, select

            cotacao = Decimal(str(settings.COTACAO_DOLAR))
            custo_brl = Decimal(str(custo_usd)) * cotacao

            registro = ConsumoApi(
                id=uuid.uuid4(),
                agente=agente,
                modelo=model,
                tier=tier,
                tokens_prompt=tokens_prompt,
                tokens_saida=tokens_saida,
                custo_usd=Decimal(str(custo_usd)),
                custo_brl=custo_brl,
                cotacao_dolar=cotacao,
                tempo_ms=tempo_ms,
                status=status,
            )

            async with async_session() as db:
                db.add(registro)
                await db.flush()

                # Checar se cruzou o threshold de alerta (mês corrente)
                from datetime import datetime
                inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                total_result = await db.execute(
                    select(func.sum(ConsumoApi.custo_brl)).where(
                        ConsumoApi.timestamp >= inicio_mes
                    )
                )
                total_mes = float(total_result.scalar() or 0)
                await db.commit()

            # Alerta Telegram se ultrapassou o limite (só dispara na primeira vez que cruza)
            threshold = settings.BUDGET_ALERT_BRL
            total_antes = total_mes - float(custo_brl)
            if total_antes < threshold <= total_mes:
                await self._enviar_alerta_orcamento(total_mes)

        except Exception as e:
            logger.warning(f"[LLM-Consumo] Falha ao registrar consumo (não crítico): {e}")

    async def _enviar_alerta_orcamento(self, total_mes: float) -> None:
        """Envia alerta Telegram quando o gasto mensal atinge BUDGET_ALERT_BRL."""
        try:
            import httpx
            if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ALLOWED_USER_IDS:
                return

            user_ids = [uid.strip() for uid in settings.TELEGRAM_ALLOWED_USER_IDS.split(",") if uid.strip()]
            budget = settings.BUDGET_BRL
            pct = (total_mes / budget) * 100

            texto = (
                f"⚠️ *Alerta de Orçamento — Escrivão AI*\n\n"
                f"Consumo mensal de API atingiu *R$ {total_mes:.2f}* "
                f"({pct:.0f}% do limite de R$ {budget:.0f}).\n\n"
                f"Acesse o dashboard em `/consumo/saldo` para detalhes."
            )

            async with httpx.AsyncClient(timeout=10.0) as client:
                for uid in user_ids:
                    await client.post(
                        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={"chat_id": uid, "text": texto, "parse_mode": "Markdown"},
                    )
        except Exception as e:
            logger.warning(f"[LLM-Alerta] Falha ao enviar alerta Telegram: {e}")

    def _estimar_custo(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimativa de custo (USD) baseada em preços por 1M tokens.

        ATENÇÃO: as chaves mais específicas devem vir ANTES das menos específicas
        (ex: gemini-2.5-flash-lite antes de gemini-2.5-flash) para evitar
        que o substring match capture o modelo errado.
        """
        # Ordenado do mais específico para o menos específico dentro de cada família
        precos = [
            # Família 2.5 (atual)
            ("gemini-2.5-flash-lite",  {"in": 0.10,   "out": 0.40}),
            ("gemini-2.5-flash",       {"in": 0.15,   "out": 0.60}),
            ("gemini-2.5-pro",         {"in": 1.25,   "out": 10.00}),
            # Família 2.0 (legado)
            ("gemini-2.0-flash-lite",  {"in": 0.075,  "out": 0.30}),
            ("gemini-2.0-flash",       {"in": 0.10,   "out": 0.40}),
            # Família 1.5 (legado)
            ("gemini-1.5-flash-8b",    {"in": 0.0375, "out": 0.15}),
            ("gemini-1.5-flash",       {"in": 0.075,  "out": 0.30}),
            ("gemini-1.5-pro",         {"in": 1.25,   "out": 5.00}),
            # Aliases antigos do SDK (sem versão explícita)
            ("gemini-pro-latest",      {"in": 0.50,   "out": 1.50}),  # era gemini-1.0-pro
            ("gemini-flash-latest",    {"in": 0.075,  "out": 0.30}),  # era gemini-1.5-flash
            ("gemini-pro",             {"in": 0.50,   "out": 1.50}),  # gemini-1.0-pro
            # Groq (Llama) — preços reais Groq por 1M tokens em USD
            ("llama-3.3-70b",          {"in": 0.59,   "out": 0.79}),
            ("llama-3.1-70b",          {"in": 0.59,   "out": 0.79}),
            ("llama-3.1-8b",           {"in": 0.05,   "out": 0.08}),
            ("llama",                  {"in": 0.20,   "out": 0.30}),  # fallback llama genérico
            # Embeddings (gratuitos)
            ("text-embedding-004",     {"in": 0.00,   "out": 0.00}),
            ("gemini-embedding",       {"in": 0.00,   "out": 0.00}),
        ]

        model_lower = model.lower()
        selected_price = {"in": 0.15, "out": 0.60}  # fallback = gemini-2.5-flash (razoável)

        for key, prices in precos:
            if key in model_lower:
                selected_price = prices
                break

        return (tokens_in  * selected_price["in"]  / 1_000_000) + \
               (tokens_out * selected_price["out"] / 1_000_000)
