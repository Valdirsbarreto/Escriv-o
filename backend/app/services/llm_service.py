"""
Escrivão AI — Serviço LLM
Roteamento unificado via Google Gemini para todos os tiers.
Econômico: gemini-1.5-flash-8b | Standard: gemini-1.5-flash | Premium: gemini-1.5-pro
"""

import logging
import time
from typing import List, Dict, Optional, Any

from google import genai
from google.genai import types as genai_types

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Gerencia chamadas a LLMs com roteamento por criticidade.

    Econômico  (gemini-1.5-flash-8b) : NER, classificação, resumos — temperature 0.1
    Standard   (gemini-1.5-flash)    : orquestração, extrato bancário, OCR
    Premium    (gemini-1.5-pro)      : copiloto RAG, fichas, cautelares, síntese investigativa
    """

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY é obrigatório — todos os tiers LLM usam Google Gemini"
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
    ) -> Dict[str, Any]:
        """
        Envia mensagens para o LLM e retorna a resposta.

        Args:
            messages: Lista de dicts com role e content
            tier: "economico", "standard" ou "premium"
            temperature: 0.0 a 1.0 (mais baixo = mais preciso)
            max_tokens: máximo de tokens na resposta
            json_mode: se True, força resposta em JSON

        Returns:
            {
                "content": str,
                "model": str,
                "tokens_prompt": int,
                "tokens_resposta": int,
                "custo_estimado": float,
                "tempo_ms": int,
            }
        """
        if tier == "economico":
            model = self.eco_model
            temperature = settings.LLM_ECONOMICO_TEMPERATURE  # 0.1 por diretriz
        elif tier == "standard":
            model = self.std_model
        else:  # "premium"
            model = self.premium_model

        return await self._gemini_completion(messages, model, temperature, max_tokens, json_mode)

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

            response = await self._genai_client.aio.models.generate_content(
                model=model,
                contents=gemini_messages,
                config=config,
            )

            tempo_ms = int((time.time() - t0) * 1000)

            content = response.text

            tokens_prompt   = response.usage_metadata.prompt_token_count     if hasattr(response, "usage_metadata") else 0
            tokens_resposta = response.usage_metadata.candidates_token_count if hasattr(response, "usage_metadata") else 0

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

    def _estimar_custo(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimativa de custo (USD) baseada em preços por 1M tokens."""
        precos = {
            "gemini-1.5-flash-8b": {"in": 0.0375, "out": 0.15},  # econômico
            "gemini-1.5-flash":    {"in": 0.075,  "out": 0.30},  # standard/vision
            "gemini-1.5-pro":      {"in": 1.25,   "out": 5.00},  # premium
            "gemini-2.0-flash":    {"in": 0.10,   "out": 0.40},  # fallback/transição
        }

        model_lower = model.lower()
        selected_price = {"in": 1.0, "out": 3.0}  # fallback genérico

        for key, prices in precos.items():
            if key in model_lower:
                selected_price = prices
                break

        return (tokens_in  * selected_price["in"]  / 1_000_000) + \
               (tokens_out * selected_price["out"] / 1_000_000)
