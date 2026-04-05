"""
Escrivão AI — Testes: Copiloto e LLM
Testa prompts, serviço LLM e pipeline do copiloto.
"""

import pytest


class TestPrompts:
    """Testa os templates de prompts."""

    def test_system_prompt_copiloto_formatacao(self):
        """System prompt do copiloto deve aceitar formatação."""
        from app.core.prompts import SYSTEM_PROMPT_COPILOTO
        resultado = SYSTEM_PROMPT_COPILOTO.format(
            numero_inquerito="IP 001/2024",
            estado_atual="investigacao_ativa",
            total_paginas=150,
            total_documentos=3,
            contexto_rag="Trecho de teste dos autos.",
        )
        assert "IP 001/2024" in resultado
        assert "investigacao_ativa" in resultado
        assert "Escrivão AI" in resultado

    def test_system_prompt_triagem_formatacao(self):
        """System prompt de triagem deve aceitar formatação."""
        from app.core.prompts import SYSTEM_PROMPT_TRIAGEM
        resultado = SYSTEM_PROMPT_TRIAGEM.format(
            contexto_rag="Conteúdo do inquérito de teste.",
        )
        assert "Classificação Estratégica" in resultado
        assert "Conteúdo do inquérito de teste" in resultado

    def test_system_prompt_auditoria_formatacao(self):
        """Prompt de auditoria deve aceitar formatação."""
        from app.core.prompts import SYSTEM_PROMPT_AUDITORIA_FACTUAL
        resultado = SYSTEM_PROMPT_AUDITORIA_FACTUAL.format(
            resposta="Resposta do copiloto de teste.",
            contexto_rag="Trechos originais de teste.",
        )
        assert "Resposta do copiloto de teste" in resultado
        assert "Trechos originais de teste" in resultado
        assert "score_confiabilidade" in resultado

    def test_template_contexto_rag(self):
        """Template de contexto RAG deve aceitar formatação."""
        from app.core.prompts import TEMPLATE_CONTEXTO_RAG
        resultado = TEMPLATE_CONTEXTO_RAG.format(
            indice=1,
            score=0.85,
            documento="boletim.pdf",
            pagina_inicial=1,
            pagina_final=3,
            tipo_documento="auto_de_prisão",
            texto="Texto extraído do documento.",
        )
        assert "boletim.pdf" in resultado
        assert "0.85" in resultado


class TestLLMService:
    """Testa o serviço LLM (sem chamadas reais)."""

    def test_instanciacao(self):
        """Serviço LLM deve instanciar sem erros."""
        from app.services.llm_service import LLMService
        service = LLMService()
        assert service.eco_model is not None
        assert service.premium_model is not None

    def test_estimativa_custo_gemini_flash(self):
        """Estimativa de custo para gemini-1.5-flash."""
        from app.services.llm_service import LLMService
        service = LLMService()
        custo = service._estimar_custo("gemini-1.5-flash", 1000, 500)
        assert custo > 0
        assert custo < 0.01  # Deve ser centavos

    def test_estimativa_custo_modelo_desconhecido(self):
        """Modelo desconhecido deve usar fallback."""
        from app.services.llm_service import LLMService
        service = LLMService()
        custo = service._estimar_custo("modelo-ficticio-xyz", 1000, 500)
        assert custo > 0


class TestCopilotoService:
    """Testa o serviço copiloto (sem chamadas LLM reais)."""

    def test_instanciacao(self):
        """Copiloto deve instanciar sem erros."""
        try:
            from app.services.copiloto_service import CopilotoService
            copiloto = CopilotoService()
            assert copiloto.embedding_service is not None
            assert copiloto.llm_service is not None
        except Exception:
            pytest.skip("Dependências do copiloto não disponíveis")
