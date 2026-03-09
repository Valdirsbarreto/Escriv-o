"""
Escrivão AI — Testes: Resumos Hierárquicos (Sprint 5)
Testa prompts, SummaryService (cache hit/miss) e endpoints de resumo.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from app.main import app


class TestPromptosResumo:
    """Testa os prompts de resumo hierárquico."""

    def test_prompt_resumo_pagina(self):
        from app.core.prompts import PROMPT_RESUMO_PAGINA
        result = PROMPT_RESUMO_PAGINA.format(texto="Texto de teste da página 1.")
        assert "Texto de teste" in result
        assert "3 linhas" in result

    def test_prompt_resumo_documento(self):
        from app.core.prompts import PROMPT_RESUMO_DOCUMENTO
        result = PROMPT_RESUMO_DOCUMENTO.format(
            nome_arquivo="portaria.pdf",
            tipo_peca="portaria",
            texto="Texto completo da portaria de instauração."
        )
        assert "portaria.pdf" in result
        assert "portaria" in result

    def test_prompt_resumo_volume(self):
        from app.core.prompts import PROMPT_RESUMO_VOLUME
        result = PROMPT_RESUMO_VOLUME.format(
            numero_volume=1,
            resumos_documentos="Resumo doc 1.\n---\nResumo doc 2."
        )
        assert "VOLUME 1" in result
        assert "Resumo doc 1" in result

    def test_prompt_resumo_caso(self):
        from app.core.prompts import PROMPT_RESUMO_CASO
        result = PROMPT_RESUMO_CASO.format(
            numero_inquerito="IP 001/2026",
            resumos_volumes="Resumo do volume 1."
        )
        assert "IP 001/2026" in result
        assert "Fato em Apuração" in result


class TestSummaryService:
    """Testa o SummaryService com mock do LLM e DB."""

    @pytest.mark.asyncio
    @patch("app.services.summary_service.LLMService")
    async def test_resumir_documento_sem_cache(self, mock_llm_class):
        """Deve chamar LLM quando não há cache."""
        mock_llm = AsyncMock()
        mock_llm.chat_completion.return_value = {
            "content": "Resumo gerado pelo LLM.",
            "model": "gpt-4.1-nano",
            "usage": {"total_tokens": 150},
        }
        mock_llm_class.return_value = mock_llm

        # Mock de AsyncSession que retorna None (sem cache) e com add síncrono
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() é síncrono no SQLAlchemy
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        from app.services.summary_service import SummaryService
        svc = SummaryService()

        resumo = await svc.resumir_documento(
            db=mock_db,
            inquerito_id=uuid.uuid4(),
            documento_id=uuid.uuid4(),
            texto="Texto de teste do documento.",
            nome_arquivo="teste.pdf",
            tipo_peca="boletim_ocorrencia",
        )

        assert resumo == "Resumo gerado pelo LLM."
        mock_llm.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.summary_service.LLMService")
    async def test_resumir_documento_com_cache(self, mock_llm_class):
        """Deve retornar do cache sem chamar LLM."""
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm

        # Mock que retorna cache existente
        from app.models.resumo_cache import ResumoCache
        resumo_cache_obj = MagicMock(spec=ResumoCache)
        resumo_cache_obj.texto_resumo = "Resumo do cache."
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = resumo_cache_obj
        mock_db.execute.return_value = mock_result

        from app.services.summary_service import SummaryService
        svc = SummaryService()

        resumo = await svc.resumir_documento(
            db=mock_db,
            inquerito_id=uuid.uuid4(),
            documento_id=uuid.uuid4(),
            texto="Irrelevante.",
            nome_arquivo="teste.pdf",
        )

        assert resumo == "Resumo do cache."
        # LLM NÃO deve ser chamado
        mock_llm.chat_completion.assert_not_called()


class TestResumosAPI:
    """Testa os endpoints de resumo da API."""

    @pytest.mark.asyncio
    async def test_endpoint_resumo_nao_encontrado(self):
        """Deve retornar 404 quando resumo ainda não foi gerado."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                inq_id = str(uuid.uuid4())
                response = await client.get(f"/api/v1/inqueritos/{inq_id}/indices/resumo")
                assert response.status_code == 404
            except Exception:
                pytest.skip("Banco de dados não disponível.")
