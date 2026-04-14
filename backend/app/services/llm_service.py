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

        result = await self._gemini_completion(messages, model, temperature, max_tokens, json_mode)

        # Registrar consumo (await direto pois roda sob asyncio.run no Celery)
        await self._registrar_consumo(
            agente=agente,
            tier=tier,
            model=model,
            tokens_prompt=result["tokens_prompt"],
            tokens_saida=result["tokens_resposta"],
            custo_usd=result["custo_estimado"],
        )

        return result

    async def _gemini_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
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

            config = genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json" if json_mode else None,
            )

            # Timeout de 180s — evita worker pendurado indefinidamente em calls lentos
            timeout_s = 300 if max_tokens >= 3000 else 180
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
        """Estimativa de custo (USD) baseada em preços por 1M tokens (Target Gemini)."""
        precos = {
            "gemini-1.5-flash-8b": {"in": 0.0375, "out": 0.15},
            "gemini-1.5-flash":    {"in": 0.075,  "out": 0.30},
            "gemini-1.5-pro":      {"in": 1.25,   "out": 5.00},
            "gemini-2.0-flash":    {"in": 0.10,   "out": 0.40},
            "text-embedding-004":  {"in": 0.00,   "out": 0.00},
        }

        model_lower = model.lower()
        selected_price = {"in": 1.0, "out": 3.0}

        for key, prices in precos.items():
            if key in model_lower:
                selected_price = prices
                break

        return (tokens_in  * selected_price["in"]  / 1_000_000) + \
               (tokens_out * selected_price["out"] / 1_000_000)
