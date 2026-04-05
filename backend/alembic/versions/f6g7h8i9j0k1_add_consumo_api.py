"""Add consumo_api table for LLM cost tracking

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-04-04 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f6g7h8i9j0k1"
down_revision: Union[str, None] = "e5f6g7h8i9j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consumo_api",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("agente", sa.String(60), nullable=False),
        sa.Column("modelo", sa.String(60), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("tokens_prompt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_saida", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("custo_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("custo_brl", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("cotacao_dolar", sa.Numeric(6, 2), nullable=False, server_default="5.80"),
    )
    op.create_index("ix_consumo_api_timestamp", "consumo_api", ["timestamp"])
    op.create_index("ix_consumo_api_agente", "consumo_api", ["agente"])
    op.create_index("ix_consumo_api_agente_timestamp", "consumo_api", ["agente", "timestamp"])

    # RLS — apenas o service role pode acessar diretamente
    op.execute("ALTER TABLE consumo_api ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY consumo_api_backend_only ON consumo_api "
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS consumo_api_backend_only ON consumo_api")
    op.drop_index("ix_consumo_api_agente_timestamp", table_name="consumo_api")
    op.drop_index("ix_consumo_api_agente", table_name="consumo_api")
    op.drop_index("ix_consumo_api_timestamp", table_name="consumo_api")
    op.drop_table("consumo_api")
