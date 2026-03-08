"""
Escrivão AI — Testes: Health Check
Verifica se o endpoint /health responde corretamente.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    """Endpoint /health deve retornar status ok."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "escrivao-ai"
    assert data["sprint"] == 1


@pytest.mark.asyncio
async def test_root():
    """Endpoint / deve retornar informações do sistema."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["nome"] == "Escrivão AI"
    assert "documentacao" in data
