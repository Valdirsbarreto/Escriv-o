"""
Escrivão AI — Testes: Auditoria
Testa o modelo Auditoria e o processo de auditoria factual do Copiloto.
"""

import json
import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.models.auditoria import Auditoria
from app.services.copiloto_service import CopilotoService


class TestAuditoriaModel:
    """Testa o modelo SQLAlchemy Auditoria."""

    def test_instanciamento_auditoria(self):
        """Deve ser capaz de instanciar o modelo de Auditoria."""
        auditoria_id = uuid.uuid4()
        tarefa_id = uuid.uuid4()
        
        auditoria = Auditoria(
            id=auditoria_id,
            tarefa_id=tarefa_id,
            tipo_auditoria="factual",
            status="pendente",
            inconsistencias_json={"falhas": []},
            aprovado_por_usuario=False
        )
        
        assert auditoria.id == auditoria_id
        assert auditoria.tarefa_id == tarefa_id
        assert auditoria.tipo_auditoria == "factual"
        assert auditoria.status == "pendente"
        assert auditoria.inconsistencias_json == {"falhas": []}
        assert "factual" in repr(auditoria)
        assert "pendente" in repr(auditoria)


@pytest.mark.asyncio
class TestAuditoriaCopiloto:
    """Testa a lógica de auditoria do CopilotoService."""

    @patch("app.services.llm_service.LLMService.chat_completion")
    async def test_auditar_resposta_valido(self, mock_chat_completion):
        """Deve auditar e retornar JSON parseado corretamente."""
        # Configurar mock para retornar uma resposta de sucesso
        json_response = {
            "status": "aprovado",
            "score_confiabilidade": 0.95,
            "inconsistencias": []
        }
        
        mock_chat_completion.return_value = {
            "content": json.dumps(json_response),
            "model": "gpt-4o-mini",
            "tokens_prompt": 100,
            "tokens_resposta": 50,
            "custo_estimado": 0.001,
        }
        
        service = CopilotoService()
        
        resultado = await service._auditar_resposta(
            resposta="A resposta do agente.",
            contexto_rag="Texto do RAG."
        )
        
        assert resultado["status"] == "aprovado"
        assert resultado["score_confiabilidade"] == 0.95
        assert resultado["modelo_auditor"] == "gpt-4o-mini"
        assert resultado["custo_auditoria"] == 0.001
        
        # O _auditar_resposta vai chamar o chat_completion usando o modelo tier "economico"
        mock_chat_completion.assert_awaited_once()
        kwargs = mock_chat_completion.await_args.kwargs
        assert kwargs["tier"] == "economico"
        assert kwargs["json_mode"] is True

    @patch("app.services.llm_service.LLMService.chat_completion")
    async def test_auditar_resposta_invalido(self, mock_chat_completion):
        """Deve tratar corretamente o caso em que o LLM não retorna JSON válido."""
        mock_chat_completion.return_value = {
            "content": "Isso não é um JSON válido e vai dar erro no parser.",
            "model": "gpt-4o-mini",
            "tokens_prompt": 100,
            "tokens_resposta": 10,
            "custo_estimado": 0.0005,
        }
        
        service = CopilotoService()
        
        resultado = await service._auditar_resposta(
            resposta="Teste devolvendo nao json",
            contexto_rag="Contexto teste"
        )
        
        assert resultado["status"] == "erro"
        assert resultado["score_confiabilidade"] is None
        assert "raw" in resultado
        assert resultado["modelo_auditor"] == "gpt-4o-mini"
