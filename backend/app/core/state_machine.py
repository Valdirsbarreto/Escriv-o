"""
Escrivão AI — Máquina de Estados do Inquérito
FSM conforme blueprint §7: define estados, transições válidas e ações por estado.
"""

from enum import Enum
from typing import Dict, List, Set


class EstadoInquerito(str, Enum):
    """Estados operacionais do inquérito."""
    RECEBIDO = "recebido"
    INDEXANDO = "indexando"
    TRIAGEM = "triagem"
    INVESTIGACAO_PRELIMINAR = "investigacao_preliminar"
    INVESTIGACAO_ATIVA = "investigacao_ativa"
    DILIGENCIAS_EXTERNAS = "diligencias_externas"
    ANALISE_FINAL = "analise_final"
    RELATORIO = "relatorio"
    ENCERRAMENTO = "encerramento"
    ARQUIVAMENTO_SUGERIDO = "arquivamento_sugerido"
    AGUARDANDO_RESPOSTA = "aguardando_resposta_externa"


# ── Transições válidas ────────────────────────────────────────────
# Mapeia: estado_atual -> {estados para os quais pode transitar}
TRANSICOES_VALIDAS: Dict[EstadoInquerito, Set[EstadoInquerito]] = {
    EstadoInquerito.RECEBIDO: {
        EstadoInquerito.INDEXANDO,
    },
    EstadoInquerito.INDEXANDO: {
        EstadoInquerito.TRIAGEM,
    },
    EstadoInquerito.TRIAGEM: {
        EstadoInquerito.INVESTIGACAO_PRELIMINAR,
        EstadoInquerito.INVESTIGACAO_ATIVA,
        EstadoInquerito.ARQUIVAMENTO_SUGERIDO,
        EstadoInquerito.ENCERRAMENTO,
    },
    EstadoInquerito.INVESTIGACAO_PRELIMINAR: {
        EstadoInquerito.INVESTIGACAO_ATIVA,
        EstadoInquerito.DILIGENCIAS_EXTERNAS,
        EstadoInquerito.TRIAGEM,
        EstadoInquerito.ANALISE_FINAL,
        EstadoInquerito.AGUARDANDO_RESPOSTA,
    },
    EstadoInquerito.INVESTIGACAO_ATIVA: {
        EstadoInquerito.DILIGENCIAS_EXTERNAS,
        EstadoInquerito.ANALISE_FINAL,
        EstadoInquerito.RELATORIO,
        EstadoInquerito.AGUARDANDO_RESPOSTA,
    },
    EstadoInquerito.DILIGENCIAS_EXTERNAS: {
        EstadoInquerito.INVESTIGACAO_ATIVA,
        EstadoInquerito.ANALISE_FINAL,
        EstadoInquerito.AGUARDANDO_RESPOSTA,
    },
    EstadoInquerito.ANALISE_FINAL: {
        EstadoInquerito.RELATORIO,
        EstadoInquerito.INVESTIGACAO_ATIVA,
    },
    EstadoInquerito.RELATORIO: {
        EstadoInquerito.ENCERRAMENTO,
        EstadoInquerito.ANALISE_FINAL,
    },
    EstadoInquerito.ENCERRAMENTO: {
        EstadoInquerito.ARQUIVAMENTO_SUGERIDO,
    },
    EstadoInquerito.ARQUIVAMENTO_SUGERIDO: set(),
    EstadoInquerito.AGUARDANDO_RESPOSTA: {
        EstadoInquerito.INVESTIGACAO_PRELIMINAR,
        EstadoInquerito.INVESTIGACAO_ATIVA,
        EstadoInquerito.DILIGENCIAS_EXTERNAS,
        EstadoInquerito.ANALISE_FINAL,
    },
}


# ── Ações permitidas por estado ───────────────────────────────────
# Define quais funcionalidades ficam habilitadas em cada fase
ACOES_POR_ESTADO: Dict[EstadoInquerito, List[str]] = {
    EstadoInquerito.RECEBIDO: [
        "upload_documentos",
    ],
    EstadoInquerito.INDEXANDO: [
        "consultar_status_indexacao",
    ],
    EstadoInquerito.TRIAGEM: [
        "copiloto",
        "triagem_rapida",
        "consultar_indices",
        "verificar_prescricao",
        "consultar_documentos",
    ],
    EstadoInquerito.INVESTIGACAO_PRELIMINAR: [
        "copiloto",
        "linhas_investigacao",
        "perguntas_oitiva",
        "sugerir_diligencias",
        "consultar_indices",
        "consultar_documentos",
        "osint_basico",
        "verificar_prescricao",
    ],
    EstadoInquerito.INVESTIGACAO_ATIVA: [
        "copiloto",
        "linhas_investigacao",
        "perguntas_oitiva",
        "sugerir_diligencias",
        "consultar_indices",
        "consultar_documentos",
        "osint_basico",
        "osint_avancado",
        "redigir_oficio",
        "redigir_despacho",
        "verificar_prescricao",
        "relatorio_parcial",
    ],
    EstadoInquerito.DILIGENCIAS_EXTERNAS: [
        "copiloto",
        "consultar_indices",
        "consultar_documentos",
        "sugerir_diligencias",
        "redigir_oficio",
        "verificar_prescricao",
    ],
    EstadoInquerito.ANALISE_FINAL: [
        "copiloto",
        "linhas_investigacao",
        "perguntas_oitiva",
        "consultar_indices",
        "consultar_documentos",
        "osint_basico",
        "osint_avancado",
        "redigir_oficio",
        "redigir_despacho",
        "relatorio_parcial",
        "relatorio_final",
        "representacao_cautelar",
        "tipificacao_provisoria",
        "verificar_prescricao",
    ],
    EstadoInquerito.RELATORIO: [
        "copiloto",
        "consultar_indices",
        "consultar_documentos",
        "relatorio_parcial",
        "relatorio_final",
        "verificar_prescricao",
    ],
    EstadoInquerito.ENCERRAMENTO: [
        "copiloto",
        "consultar_indices",
        "consultar_documentos",
        "relatorio_final",
    ],
    EstadoInquerito.ARQUIVAMENTO_SUGERIDO: [
        "consultar_indices",
        "consultar_documentos",
    ],
    EstadoInquerito.AGUARDANDO_RESPOSTA: [
        "copiloto",
        "consultar_indices",
        "consultar_documentos",
        "redigir_oficio",
        "verificar_prescricao",
    ],
}


class StateMachineError(Exception):
    """Erro de transição inválida na máquina de estados."""
    pass


def validar_transicao(estado_atual: str, novo_estado: str) -> bool:
    """
    Verifica se a transição de estado é válida.
    Retorna True se válida, False caso contrário.
    """
    try:
        atual = EstadoInquerito(estado_atual)
        novo = EstadoInquerito(novo_estado)
    except ValueError:
        return False

    return novo in TRANSICOES_VALIDAS.get(atual, set())


def obter_acoes_disponiveis(estado: str) -> List[str]:
    """Retorna a lista de ações permitidas para o estado informado."""
    try:
        estado_enum = EstadoInquerito(estado)
    except ValueError:
        return []

    return ACOES_POR_ESTADO.get(estado_enum, [])


def obter_transicoes_possiveis(estado: str) -> List[str]:
    """Retorna os estados para os quais é possível transitar."""
    try:
        estado_enum = EstadoInquerito(estado)
    except ValueError:
        return []

    return [e.value for e in TRANSICOES_VALIDAS.get(estado_enum, set())]


# ── Descrições amigáveis dos estados ─────────────────────────────
DESCRICAO_ESTADOS: Dict[EstadoInquerito, str] = {
    EstadoInquerito.RECEBIDO: "Inquérito recebido, aguardando upload de documentos",
    EstadoInquerito.INDEXANDO: "Documentos sendo processados e indexados",
    EstadoInquerito.TRIAGEM: "Pronto para triagem inicial",
    EstadoInquerito.INVESTIGACAO_PRELIMINAR: "Em investigação preliminar",
    EstadoInquerito.INVESTIGACAO_ATIVA: "Investigação em andamento",
    EstadoInquerito.DILIGENCIAS_EXTERNAS: "Aguardando resultado de diligências",
    EstadoInquerito.ANALISE_FINAL: "Em análise final para conclusão",
    EstadoInquerito.RELATORIO: "Em fase de elaboração de relatório",
    EstadoInquerito.ENCERRAMENTO: "Em processo de encerramento",
    EstadoInquerito.ARQUIVAMENTO_SUGERIDO: "Arquivamento sugerido",
    EstadoInquerito.AGUARDANDO_RESPOSTA: "Aguardando resposta de órgão externo",
}
