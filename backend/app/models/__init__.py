"""
Escrivão AI — Models package
Importa todos os modelos para que Alembic os detecte automaticamente.
"""

from app.models.inquerito import Inquerito
from app.models.documento import Documento
from app.models.chunk import Chunk
from app.models.pessoa import Pessoa
from app.models.estado_inquerito import TransicaoEstado
from app.models.tarefa_agente import TarefaAgente
from app.models.auditoria import Auditoria
from app.models.volume import Volume
from app.models.log_ingestao import LogIngestao
from app.models.sessao_chat import SessaoChat
from app.models.mensagem_chat import MensagemChat

__all__ = [
    "Inquerito",
    "Documento",
    "Chunk",
    "Pessoa",
    "TransicaoEstado",
    "TarefaAgente",
    "Auditoria",
    "Volume",
    "LogIngestao",
    "SessaoChat",
    "MensagemChat",
]
