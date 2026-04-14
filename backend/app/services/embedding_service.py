"""
Escrivão AI — Serviço de Embeddings
Geração de embeddings via API do Google Gemini (gemini-embedding-001).
Substituiu o sentence-transformers local para economizar RAM e reduzir tempo de build.
Dimensões: 768 (via outputDimensionality para manter compatibilidade com coleção Qdrant).

NOTA: O SDK google-genai 1.x (sync e async) usa v1beta por padrão e causa 404.
text-embedding-004 não está disponível para esta chave de API.
Modelos disponíveis confirmados: gemini-embedding-001, gemini-embedding-2-preview.
Fix definitivo: chamar a REST API diretamente via httpx na v1beta, sem SDK.
Nunca usar self._client.models.embed_content nem aio.models.
"""

import logging
from typing import List

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-embedding-001"
DEFAULT_VECTOR_SIZE = 768
_EMBED_URL = "https://generativelanguage.googleapis.com/v1/models/{model}:embedContent"
_BATCH_URL = "https://generativelanguage.googleapis.com/v1/models/{model}:batchEmbedContents"


class EmbeddingService:
    """Gera embeddings vetoriais via REST API do Google (v1 direto, sem SDK)."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.vector_size = DEFAULT_VECTOR_SIZE
        self._api_key = settings.GEMINI_API_KEY

    def generate(self, text: str) -> List[float]:
        """Gera embedding para um único texto (síncrono — use em workers/threads)."""
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        text = str(text).replace("\x00", "").strip()
        if not text:
            return [0.0] * self.vector_size

        url = _EMBED_URL.format(model=self.model_name)
        payload = {
            "model": f"models/{self.model_name}",
            "content": {"parts": [{"text": text[:8000]}]},
            "outputDimensionality": self.vector_size,
        }
        try:
            resp = httpx.post(url, params={"key": self._api_key}, json=payload, timeout=30)
            if not resp.is_success:
                logger.error(
                    f"[EMBEDDINGS] HTTP {resp.status_code} ao gerar embedding: {resp.text[:500]}"
                )
                return [0.0] * self.vector_size
            return resp.json()["embedding"]["values"]
        except Exception as e:
            logger.error(f"[EMBEDDINGS] Erro ao gerar embedding: {e}")
            return [0.0] * self.vector_size

    async def agenerate(self, text: str) -> List[float]:
        """Gera embedding de forma async — use em endpoints FastAPI."""
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        text = str(text).replace("\x00", "").strip()
        if not text:
            return [0.0] * self.vector_size

        url = _EMBED_URL.format(model=self.model_name)
        payload = {
            "model": f"models/{self.model_name}",
            "content": {"parts": [{"text": text[:8000]}]},
            "outputDimensionality": self.vector_size,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, params={"key": self._api_key}, json=payload)
                if not resp.is_success:
                    logger.error(
                        f"[EMBEDDINGS] HTTP {resp.status_code} ao gerar embedding async: {resp.text[:500]}"
                    )
                    return [0.0] * self.vector_size
                return resp.json()["embedding"]["values"]
        except Exception as e:
            logger.error(f"[EMBEDDINGS] Erro ao gerar embedding async: {e}")
            return [0.0] * self.vector_size

    def generate_batch(
        self,
        texts: List[str],
        batch_size: int = 64,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """Gera embeddings em lote via batchEmbedContents (REST v1 direto)."""
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        all_embeddings: List[List[float]] = []
        url = _BATCH_URL.format(model=self.model_name)

        for i in range(0, len(texts), batch_size):
            batch = [str(t).replace("\x00", "").strip() or " " for t in texts[i:i + batch_size]]
            payload = {
                "requests": [
                    {
                        "model": f"models/{self.model_name}",
                        "content": {"parts": [{"text": t[:8000]}]},
                        "outputDimensionality": self.vector_size,
                    }
                    for t in batch
                ]
            }
            try:
                resp = httpx.post(url, params={"key": self._api_key}, json=payload, timeout=60)
                resp.raise_for_status()
                batch_vecs = [e["values"] for e in resp.json()["embeddings"]]
                all_embeddings.extend(batch_vecs)
            except Exception as e:
                logger.error(f"[EMBEDDINGS] Erro no batch {i}: {e}")
                all_embeddings.extend([[0.0] * self.vector_size] * len(batch))

        return all_embeddings

    def get_vector_size(self) -> int:
        """Retorna o tamanho do vetor do modelo."""
        return self.vector_size
