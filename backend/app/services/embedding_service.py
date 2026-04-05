"""
Escrivão AI — Serviço de Embeddings
Geração de embeddings via API do Google Gemini (text-embedding-004).
Substituiu o sentence-transformers local para economizar RAM e reduzir tempo de build.
Dimensões: 768.
"""

import logging
from typing import List, Optional

from google import genai
from google.genai import types as genai_types

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "text-multilingual-embedding-002"
DEFAULT_VECTOR_SIZE = 768


class EmbeddingService:
    """Gera embeddings vetoriais via API do Google."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.vector_size = DEFAULT_VECTOR_SIZE
        self._client = (
            genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=genai_types.HttpOptions(api_version="v1beta"),
            )
            if settings.GEMINI_API_KEY
            else None
        )

    def generate(self, text: str) -> List[float]:
        """Gera embedding para um único texto (chamada síncrona — use em workers/threads)."""
        if not self._client:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        text = str(text).replace("\x00", "").strip()
        if not text:
            return [0.0] * self.vector_size

        try:
            result = self._client.models.embed_content(
                model=self.model_name,
                contents=text[:8000],
            )
            return result.embeddings[0].values
        except Exception as e:
            logger.error(f"[EMBEDDINGS] Erro ao gerar embedding: {e}")
            return [0.0] * self.vector_size

    async def agenerate(self, text: str) -> List[float]:
        """Gera embedding de forma async — use em endpoints FastAPI."""
        if not self._client:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        text = str(text).replace("\x00", "").strip()
        if not text:
            return [0.0] * self.vector_size

        try:
            result = await self._client.aio.models.embed_content(
                model=self.model_name,
                contents=text[:8000],
            )
            return result.embeddings[0].values
        except Exception as e:
            logger.error(f"[EMBEDDINGS] Erro ao gerar embedding async: {e}")
            return [0.0] * self.vector_size

    def generate_batch(
        self,
        texts: List[str],
        batch_size: int = 64,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """
        Gera embeddings em lote via API.
        """
        if not self._client:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = [str(t).replace("\x00", "").strip() for t in texts[i:i + batch_size]]
            batch = [t if t else " " for t in batch]
            
            try:
                result = self._client.models.embed_content(
                    model=self.model_name,
                    contents=batch,
                )
                batch_vecs = [e.values for e in result.embeddings]
                all_embeddings.extend(batch_vecs)
            except Exception as e:
                logger.error(f"[EMBEDDINGS] Erro no batch {i}: {e}")
                all_embeddings.extend([[0.0] * self.vector_size] * len(batch))

        return all_embeddings

    def get_vector_size(self) -> int:
        """Retorna o tamanho do vetor do modelo."""
        return self.vector_size
