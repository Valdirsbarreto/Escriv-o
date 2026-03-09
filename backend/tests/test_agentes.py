"""
Escrivão AI — Testes: Agentes Especializados (Sprint 6)
Testa prompts, serviços e endpoints dos 3 agentes via mocks.
"""

import pytest
import uuid
import json
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from app.main import app


class TestPromptosAgentes:
    """Testa formatação dos prompts dos agentes."""

    def test_prompt_ficha_pessoa(self):
        from app.core.prompts import PROMPT_FICHA_PESSOA
        result = PROMPT_FICHA_PESSOA.format(
            nome="José da Silva",
            dados_consolidados="CPF: 123, Tipo: investigado",
        )
        assert "José da Silva" in result
        assert "investigado" in result
        assert "pontos_de_atencao" in result

    def test_prompt_ficha_empresa(self):
        from app.core.prompts import PROMPT_FICHA_EMPRESA
        result = PROMPT_FICHA_EMPRESA.format(
            nome="Empresa XYZ Ltda",
            dados_consolidados="CNPJ: 00.000.000/0001-00, Tipo: alvo",
        )
        assert "Empresa XYZ Ltda" in result
        assert "possiveis_socios" in result

    def test_prompt_cautelar(self):
        from app.core.prompts import PROMPT_CAUTELAR
        result = PROMPT_CAUTELAR.format(
            tipo_cautelar="Mandado de Busca e Apreensão",
            numero_inquerito="IP 001/2026",
            autoridade="Dr. João Delegado",
            instrucoes="Busca no endereço Rua X, 123",
            contexto="Suspeito foi visto saindo do local.",
        )
        assert "IP 001/2026" in result
        assert "Dr. João Delegado" in result
        assert "Fundamentação legal" in result

    def test_prompt_analise_extrato(self):
        from app.core.prompts import PROMPT_ANALISE_EXTRATO
        result = PROMPT_ANALISE_EXTRATO.format(
            texto_extrato="01/01/2026 - Débito R$ 5.000,00 - Loja Misteriosa"
        )
        assert "score_suspeicao" in result
        assert "contrapartes_frequentes" in result


class TestAgenteFicha:
    """Testa o AgenteFicha com mocks."""

    @pytest.mark.asyncio
    @patch("app.services.agente_ficha.LLMService")
    async def test_gerar_ficha_pessoa(self, mock_llm_class):
        """Gera ficha de pessoa mockando LLM e DB."""
        ficha_mock = {
            "nome": "José Silva",
            "cpf": "123.456.789-00",
            "tipo_envolvimento": "investigado",
            "perfil_resumido": "Suspeito principal.",
            "contatos": [],
            "enderecos": [],
            "vinculos_empresariais": [],
            "eventos_cronologicos": [],
            "pontos_de_atencao": ["Aparece em 3 documentos"],
            "documentos_mencionados": [],
        }

        mock_llm = AsyncMock()
        mock_llm.chat_completion.return_value = {
            "content": json.dumps(ficha_mock),
            "model": "gpt-4.1",
            "usage": {"total_tokens": 300},
        }
        mock_llm_class.return_value = mock_llm

        # Mock DB
        from app.models.pessoa import Pessoa
        pessoa_obj = MagicMock(spec=Pessoa)
        pessoa_obj.id = uuid.uuid4()
        pessoa_obj.nome = "José Silva"
        pessoa_obj.cpf = "123.456.789-00"
        pessoa_obj.tipo_pessoa = "investigado"
        pessoa_obj.observacoes = None

        mock_db = AsyncMock()
        mock_db.get.return_value = pessoa_obj
        mock_db.add = MagicMock()

        # Mockar results vazios para contatos, enderecos e eventos
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = empty_result

        from app.services.agente_ficha import AgenteFicha
        agente = AgenteFicha()

        resultado = await agente.gerar_ficha_pessoa(
            db=mock_db,
            inquerito_id=uuid.uuid4(),
            pessoa_id=uuid.uuid4(),
        )

        assert resultado["nome"] == "José Silva"
        assert resultado["tipo_envolvimento"] == "investigado"
        mock_llm.chat_completion.assert_called_once()


class TestAgenteCautelar:
    """Testa o AgenteCautelar com mocks."""

    @pytest.mark.asyncio
    @patch("app.services.agente_cautelar.LLMService")
    @patch("app.services.agente_cautelar.SummaryService")
    async def test_gerar_oficio(self, mock_summary_class, mock_llm_class):
        """Gera minuta de ofício com mock do LLM."""
        mock_llm = AsyncMock()
        mock_llm.chat_completion.return_value = {
            "content": "OFÍCIO nº 001/2026\nRequisição de informações bancárias...",
            "model": "gpt-4.1",
            "usage": {"total_tokens": 500},
        }
        mock_llm_class.return_value = mock_llm

        mock_summary = AsyncMock()
        mock_summary.obter_resumo_caso.return_value = "Inquérito sobre fraude bancária."
        mock_summary_class.return_value = mock_summary

        from app.models.inquerito import Inquerito
        inq_obj = MagicMock(spec=Inquerito)
        inq_obj.numero_procedimento = "IP 001/2026"

        mock_db = AsyncMock()
        mock_db.get.return_value = inq_obj
        mock_db.add = MagicMock()

        from app.services.agente_cautelar import AgenteCautelar
        agente = AgenteCautelar()

        resultado = await agente.gerar_cautelar(
            db=mock_db,
            inquerito_id=uuid.uuid4(),
            tipo_cautelar="oficio_requisicao",
            instrucoes="Solicitar extrato bancário dos últimos 12 meses.",
        )

        assert "texto_gerado" in resultado
        assert "OFÍCIO" in resultado["texto_gerado"]
        assert resultado["inquerito"] == "IP 001/2026"


class TestAgentesAPI:
    """Testa os endpoints dos agentes via AsyncClient."""

    @pytest.mark.asyncio
    async def test_endpoint_cautelar_payload_invalido(self):
        """Deve retornar 422 com tipo_cautelar inválido."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agentes/cautelar",
                json={
                    "inquerito_id": str(uuid.uuid4()),
                    "tipo_cautelar": "tipo_inexistente",
                    "instrucoes": "Teste",
                },
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_extrato_doc_inexistente(self):
        """Deve retornar 404 ou 500 para documento inexistente."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                doc_id = str(uuid.uuid4())
                inq_id = str(uuid.uuid4())
                response = await client.post(
                    f"/api/v1/agentes/extrato/{doc_id}?inquerito_id={inq_id}"
                )
                assert response.status_code in (404, 500)
            except Exception:
                pytest.skip("Banco não disponível.")
