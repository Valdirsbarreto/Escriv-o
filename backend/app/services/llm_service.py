"""
Escrivão AI — Serviço LLM
Wrapper para chamadas a LLMs via API OpenAI-compatível.
Roteamento automático: econômico para tarefas simples, standard para balanceado, premium para críticas.
Conforme blueprint §9: Estratégia de LLMs.
"""

import logging
import time
from typing import List, Dict, Optional, Any

import httpx
from google import genai
from google.genai import types as genai_types

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Gerencia chamadas a LLMs com roteamento por criticidade.

    Modelos econômicos: resumos simples, classificação rápida (DeepSeek)
    Modelos standard: análise de contexto, resumos médios (Gemini Flash)
    Modelos premium: análise jurídica crítica, orquestração (Gemini Pro)
    """

    def __init__(self):
        self.eco_model = settings.LLM_ECONOMICO_MODEL
        self.eco_base_url = settings.LLM_ECONOMICO_BASE_URL
        self.eco_api_key = settings.LLM_ECONOMICO_API_KEY
        self.eco_provider = settings.LLM_ECONOMICO_PROVIDER

        self.std_model = settings.LLM_STANDARD_MODEL
        self.std_base_url = settings.LLM_STANDARD_BASE_URL
        self.std_api_key = settings.LLM_STANDARD_API_KEY
        self.std_provider = settings.LLM_STANDARD_PROVIDER

        self.premium_model = settings.LLM_PREMIUM_MODEL
        self.premium_base_url = settings.LLM_PREMIUM_BASE_URL
        self.premium_api_key = settings.LLM_PREMIUM_API_KEY
        self.premium_provider = settings.LLM_PREMIUM_PROVIDER

        self._genai_client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

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
            base_url = self.eco_base_url
            api_key = self.eco_api_key
            provider = self.eco_provider
        elif tier == "standard":
            model = self.std_model
            base_url = self.std_base_url
            api_key = self.std_api_key
            provider = self.std_provider
        else:
            model = self.premium_model
            base_url = self.premium_base_url
            api_key = self.premium_api_key
            provider = self.premium_provider

        if provider == "google" or "gemini" in model.lower():
            return await self._gemini_completion(messages, model, temperature, max_tokens, json_mode)

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

    async def _gemini_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Dict[str, Any]:
        """Chamada específica para a API do Google Gemini."""
        t0 = time.time()
        try:
            # Converter formato de mensagens para Gemini
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

            response = self._genai_client.models.generate_content(
                model=model,
                contents=gemini_messages,
                config=config,
            )

            tempo_ms = int((time.time() - t0) * 1000)
            
            content = response.text
            
            # Gemini SDK não expõe tokens de uso de forma tão direta na resposta simples
            # Mas podemos estimar ou tentar pegar do metadata se disponível
            tokens_prompt = response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else 0
            tokens_resposta = response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') else 0

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
            logger.error(f"[LLM-Gemini] Erro: {e}")
            raise

    def _estimar_custo(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimativa de custo (USD) baseada em preços médios por 1M tokens."""
        precos = {
            "gpt-4o-mini": {"in": 0.15, "out": 0.60},
            "gpt-4o": {"in": 2.50, "out": 10.00},
            "gemini-1.5-flash": {"in": 0.075, "out": 0.30},
            "gemini-1.5-pro": {"in": 1.25, "out": 5.00},
            "gemini-2.0-flash": {"in": 0.10, "out": 0.40},
            "deepseek-chat": {"in": 0.14, "out": 0.28},
            "deepseek": {"in": 0.14, "out": 0.28},
            "claude-3-5-sonnet": {"in": 3.00, "out": 15.00},
        }

        model_lower = model.lower()
        
        # Encontrar a melhor correspondência de preço
        selected_price = {"in": 1.0, "out": 3.0} # Fallback genérico ($1/$3 per 1M)
        
        for key, prices in precos.items():
            if key in model_lower:
                selected_price = prices
                break
        
        custo = (tokens_in * selected_price["in"] / 1_000_000) + \
                (tokens_out * selected_price["out"] / 1_000_000)
        
        return custo
