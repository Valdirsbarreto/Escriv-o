"""
Escrivão AI — Testes: Máquina de Estados
Verifica transições válidas e inválidas da FSM do inquérito.
"""

import pytest

from app.core.state_machine import (
    EstadoInquerito,
    validar_transicao,
    obter_acoes_disponiveis,
    obter_transicoes_possiveis,
    DESCRICAO_ESTADOS,
)


class TestTransicoesValidas:
    """Testa transições que devem ser permitidas."""

    def test_recebido_para_indexando(self):
        assert validar_transicao("recebido", "indexando") is True

    def test_indexando_para_triagem(self):
        assert validar_transicao("indexando", "triagem") is True

    def test_triagem_para_investigacao_preliminar(self):
        assert validar_transicao("triagem", "investigacao_preliminar") is True

    def test_triagem_para_investigacao_ativa(self):
        assert validar_transicao("triagem", "investigacao_ativa") is True

    def test_investigacao_ativa_para_analise_final(self):
        assert validar_transicao("investigacao_ativa", "analise_final") is True

    def test_investigacao_ativa_para_relatorio(self):
        assert validar_transicao("investigacao_ativa", "relatorio") is True

    def test_analise_final_para_relatorio(self):
        assert validar_transicao("analise_final", "relatorio") is True

    def test_relatorio_para_encerramento(self):
        assert validar_transicao("relatorio", "encerramento") is True

    def test_encerramento_para_arquivamento(self):
        assert validar_transicao("encerramento", "arquivamento_sugerido") is True

    def test_aguardando_para_investigacao_ativa(self):
        assert validar_transicao("aguardando_resposta_externa", "investigacao_ativa") is True


class TestTransicoesInvalidas:
    """Testa transições que devem ser bloqueadas."""

    def test_recebido_para_triagem(self):
        """Não pode pular indexação."""
        assert validar_transicao("recebido", "triagem") is False

    def test_recebido_para_relatorio(self):
        """Não pode ir direto para relatório."""
        assert validar_transicao("recebido", "relatorio") is False

    def test_arquivamento_para_qualquer(self):
        """Arquivamento é estado terminal."""
        assert validar_transicao("arquivamento_sugerido", "recebido") is False
        assert validar_transicao("arquivamento_sugerido", "triagem") is False

    def test_indexando_para_investigacao(self):
        """Não pode investigar antes da triagem."""
        assert validar_transicao("indexando", "investigacao_ativa") is False

    def test_estado_invalido(self):
        """Estados inexistentes devem retornar False."""
        assert validar_transicao("inexistente", "triagem") is False
        assert validar_transicao("recebido", "inexistente") is False


class TestAcoesDisponiveis:
    """Testa ações disponíveis por estado."""

    def test_recebido_permite_upload(self):
        acoes = obter_acoes_disponiveis("recebido")
        assert "upload_documentos" in acoes

    def test_recebido_nao_permite_copiloto(self):
        acoes = obter_acoes_disponiveis("recebido")
        assert "copiloto" not in acoes

    def test_triagem_permite_copiloto(self):
        acoes = obter_acoes_disponiveis("triagem")
        assert "copiloto" in acoes

    def test_investigacao_ativa_permite_osint(self):
        acoes = obter_acoes_disponiveis("investigacao_ativa")
        assert "osint_basico" in acoes
        assert "osint_avancado" in acoes

    def test_analise_final_permite_cautelar(self):
        acoes = obter_acoes_disponiveis("analise_final")
        assert "representacao_cautelar" in acoes

    def test_triagem_nao_permite_cautelar(self):
        acoes = obter_acoes_disponiveis("triagem")
        assert "representacao_cautelar" not in acoes

    def test_estado_invalido_retorna_vazio(self):
        acoes = obter_acoes_disponiveis("inexistente")
        assert acoes == []


class TestTransicoesPossiveis:
    """Testa lista de transições possíveis."""

    def test_recebido_transicoes(self):
        transicoes = obter_transicoes_possiveis("recebido")
        assert "indexando" in transicoes
        assert len(transicoes) == 1

    def test_triagem_transicoes(self):
        transicoes = obter_transicoes_possiveis("triagem")
        assert "investigacao_preliminar" in transicoes
        assert "investigacao_ativa" in transicoes

    def test_arquivamento_sem_transicoes(self):
        transicoes = obter_transicoes_possiveis("arquivamento_sugerido")
        assert transicoes == []


class TestDescricaoEstados:
    """Testa que todos os estados têm descrição."""

    def test_todos_estados_tem_descricao(self):
        for estado in EstadoInquerito:
            assert estado in DESCRICAO_ESTADOS
            assert len(DESCRICAO_ESTADOS[estado]) > 0
