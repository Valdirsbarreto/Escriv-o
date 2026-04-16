"""Add custos_externos table for manual external service cost tracking

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-04-16 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "custos_externos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("servico", sa.String(40), nullable=False),   # "vercel", "supabase", "railway", "serper"
        sa.Column("mes", sa.String(7), nullable=False),         # "2026-04"
        sa.Column("custo_usd", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("custo_brl", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("observacao", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("servico", "mes", name="uq_custos_externos_servico_mes"),
    )


def downgrade() -> None:
    op.drop_table("custos_externos")
