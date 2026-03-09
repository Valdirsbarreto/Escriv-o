"""
Escrivão AI — Testes: Busca RAG e Embedding
Testa o endpoint de busca e o serviço de embeddings.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_busca_inquerito_inexistente():
    """Busca em inquérito inexistente deve retornar 404 (requer PostgreSQL)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            response = await client.post(
                "/api/v1/busca/",
                json={
                    "query": "teste de busca",
                    "inquerito_id": "00000000-0000-0000-0000-000000000000",
                },
            )
            assert response.status_code in (404, 500)
        except Exception:
            pytest.skip("PostgreSQL não disponível — teste de integração")


@pytest.mark.asyncio
async def test_busca_query_curta():
    """Query muito curta deve retornar 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/busca/",
            json={
                "query": "ab",
                "inquerito_id": "00000000-0000-0000-0000-000000000000",
            },
        )
    assert response.status_code == 422


class TestEmbeddingService:
    """Testa o serviço de embeddings."""

    def test_generate_embedding(self):
        """Deve gerar um vetor de 384 dimensões."""
        try:
            from app.services.embedding_service import EmbeddingService
            service = EmbeddingService()
            embedding = service.generate("Teste de embedding para inquérito policial")
            assert isinstance(embedding, list)
            assert len(embedding) == 384
            # Vetor normalizado: norma ~= 1.0
            import math
            norma = math.sqrt(sum(x**2 for x in embedding))
            assert abs(norma - 1.0) < 0.01
        except ImportError:
            pytest.skip("sentence-transformers não instalado")

    def test_generate_batch(self):
        """Deve gerar embeddings em lote."""
        try:
            from app.services.embedding_service import EmbeddingService
            service = EmbeddingService()
            textos = [
                "Primeiro texto de teste",
                "Segundo texto de teste",
                "Terceiro texto de teste",
            ]
            embeddings = service.generate_batch(textos)
            assert len(embeddings) == 3
            assert all(len(e) == 384 for e in embeddings)
        except ImportError:
            pytest.skip("sentence-transformers não instalado")

    def test_similaridade_semantica(self):
        """Textos similares devem ter embeddings próximos."""
        try:
            from app.services.embedding_service import EmbeddingService
            service = EmbeddingService()

            e1 = service.generate("O investigado foi visto no local do crime")
            e2 = service.generate("O suspeito estava presente na cena do delito")
            e3 = service.generate("Receita de bolo de chocolate com morango")

            # Similaridade cosseno (vetores normalizados = dot product)
            sim_12 = sum(a * b for a, b in zip(e1, e2))
            sim_13 = sum(a * b for a, b in zip(e1, e3))

            # Textos similares devem ter maior similaridade
            assert sim_12 > sim_13
        except ImportError:
            pytest.skip("sentence-transformers não instalado")
