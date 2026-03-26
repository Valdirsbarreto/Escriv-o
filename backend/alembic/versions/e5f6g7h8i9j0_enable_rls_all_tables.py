"""Enable RLS on all public tables — block anonymous PostgREST access

Supabase expõe todas as tabelas via PostgREST. Sem RLS, qualquer pessoa com
a anon/service_role key pode ler ou escrever dados diretamente. O backend usa
conexão direta ao banco (DATABASE_URL) e não é afetado por RLS.

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-03-25 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5f6g7h8i9j0"
down_revision: Union[str, None] = "d4e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Todas as tabelas da aplicação expostas via PostgREST
_TABLES = [
    "inqueritos",
    "intimacoes",
    "documentos",
    "pessoas",
    "empresas",
    "delegacias",
    "contatos",
    "enderecos",
    "volumes",
    "chunks",
    "eventos_cronologicos",
    "transicoes_estado",
    "tarefas_agentes",
    "resultados_agentes",
    "resumos_cache",
    "sessoes_chat",
    "mensagens_chat",
    "logs_ingestao",
    "auditorias",
    "consultas_externas",
    "alembic_version",
]


def upgrade() -> None:
    for table in _TABLES:
        # Habilita RLS — sem nenhuma policy, acesso via PostgREST é bloqueado por padrão.
        # O backend conecta via role do banco diretamente e bypassa RLS (BYPASSRLS privilege).
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;")
