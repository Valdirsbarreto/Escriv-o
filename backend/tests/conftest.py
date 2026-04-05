"""
Fixtures globais para os testes — configuração mínima sem serviços externos.
"""
import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def fake_gemini_key(monkeypatch):
    """Injeta uma chave Gemini falsa para testes unitários que instanciam LLMService."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key-for-unit-tests")
    # Patcha diretamente o singleton settings (já criado no import)
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "fake-test-key-for-unit-tests")
    # Patcheia o genai.Client para não tentar conectar de verdade
    with patch("google.genai.Client", return_value=MagicMock()):
        yield
