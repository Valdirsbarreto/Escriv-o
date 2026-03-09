"""
Escrivão AI — Serviço de Embeddings
Geração de embeddings com sentence-transformers (local, custo zero).
Modelo padrão: all-MiniLM-L6-v2 (384 dimensões, rápido e eficiente).
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Singleton do modelo para evitar carregamento repetido
_model = None
_model_name = None

DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_VECTOR_SIZE = 384


def _get_model(model_name: str = DEFAULT_MODEL):
    """Carrega o modelo de embeddings (singleton)."""
    global _model, _model_name

    if _model is None or _model_name != model_name:
        logger.info(f"[EMBEDDINGS] Carregando modelo: {model_name}")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
        _model_name = model_name
        logger.info(f"[EMBEDDINGS] Modelo carregado: {model_name}")

    return _model


class EmbeddingService:
    """Gera embeddings vetoriais a partir de texto."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.vector_size = DEFAULT_VECTOR_SIZE

    def generate(self, text: str) -> List[float]:
        """Gera embedding para um único texto."""
        model = _get_model(self.model_name)
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def generate_batch(
        self,
        texts: List[str],
        batch_size: int = 64,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """
        Gera embeddings em lote para performance.
        Otimizado para inquéritos grandes (3000+ páginas = ~500+ chunks).
        """
        model = _get_model(self.model_name)
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
        )
        return [e.tolist() for e in embeddings]

    def get_vector_size(self) -> int:
        """Retorna o tamanho do vetor do modelo."""
        return self.vector_size
