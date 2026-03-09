"""
Escrivão AI — Serviço LLM
Wrapper para chamadas a LLMs via API OpenAI-compatível.
Roteamento automático: econômico para tarefas simples, premium para tarefas críticas.
Conforme blueprint §9: Estratégia de LLMs.
"""

import logging
import time
from typing import List, Dict, Optional, Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Gerencia chamadas a LLMs com roteamento por criticidade.

    Modelos econômicos: resumos, classificação, extração simples
    Modelos premium: análise jurídica, copiloto, decisões críticas
    """

    def __init__(self):
        self.eco_model = settings.LLM_ECONOMICO_MODEL
        self.eco_base_url = settings.LLM_ECONOMICO_BASE_URL
        self.eco_api_key = settings.LLM_ECONOMICO_API_KEY

        self.premium_model = settings.LLM_PREMIUM_MODEL
        self.premium_base_url = settings.LLM_PREMIUM_BASE_URL
        self.premium_api_key = settings.LLM_PREMIUM_API_KEY

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
            tier: "economico" ou "premium"
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
            base_url = self.eco_base_url
            api_key = self.eco_api_key
        else:
            model = self.premium_model
            base_url = self.premium_base_url
            api_key = self.premium_api_key

        url = f"{base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        t0 = time.time()

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            tempo_ms = int((time.time() - t0) * 1000)

            choice = data["choices"][0]
            usage = data.get("usage", {})

            tokens_prompt = usage.get("prompt_tokens", 0)
            tokens_resposta = usage.get("completion_tokens", 0)

            # Estimativa de custo simplificada (USD por 1M tokens)
            custo = self._estimar_custo(model, tokens_prompt, tokens_resposta)

            result = {
                "content": choice["message"]["content"],
                "model": model,
                "tokens_prompt": tokens_prompt,
                "tokens_resposta": tokens_resposta,
                "custo_estimado": custo,
                "tempo_ms": tempo_ms,
            }

            logger.info(
                f"[LLM] {model} — {tokens_prompt}+{tokens_resposta} tokens, "
                f"{tempo_ms}ms, ~${custo:.4f}"
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"[LLM] Erro HTTP {e.response.status_code}: {e.response.text[:200]}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"[LLM] Erro de conexão com {base_url}: {e}")
            raise
        except Exception as e:
            logger.error(f"[LLM] Erro inesperado: {e}")
            raise

    def _estimar_custo(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimativa de custo (USD) baseada em preços médios."""
        # Preços por 1M tokens (aproximados)
        precos = {
            "gpt-4o-mini": {"in": 0.15, "out": 0.60},
            "gpt-4o": {"in": 2.50, "out": 10.00},
            "gpt-4-turbo": {"in": 10.00, "out": 30.00},
            "gemini-2.0-flash": {"in": 0.10, "out": 0.40},
            "gemini-2.5-pro": {"in": 1.25, "out": 10.00},
            "claude-3-5-sonnet": {"in": 3.00, "out": 15.00},
            "claude-3-5-haiku": {"in": 0.80, "out": 4.00},
            "deepseek-chat": {"in": 0.14, "out": 0.28},
        }

        # Busca pelo nome parcial
        model_lower = model.lower()
        for key, prices in precos.items():
            if key in model_lower:
                return (
                    tokens_in * prices["in"] / 1_000_000
                    + tokens_out * prices["out"] / 1_000_000
                )

        # Fallback genérico
        return (tokens_in * 1.0 + tokens_out * 3.0) / 1_000_000
