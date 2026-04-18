"""add_telemetria_consumo_api

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-04-18

Adiciona colunas de telemetria à tabela consumo_api:
- tempo_ms: latência real da chamada LLM em milissegundos
- status: resultado da chamada (ok | timeout | erro)

Permite identificar agentes lentos e timeouts recorrentes.
"""

from alembic import op
import sqlalchemy as sa

revision = "o5p6q7r8s9t0"
down_revision = "n4o5p6q7r8s9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consumo_api",
        sa.Column("tempo_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "consumo_api",
        sa.Column("status", sa.String(length=20), nullable=True, server_default="ok"),
    )


def downgrade() -> None:
    op.drop_column("consumo_api", "status")
    op.drop_column("consumo_api", "tempo_ms")
