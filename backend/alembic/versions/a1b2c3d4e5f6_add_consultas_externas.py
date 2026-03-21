"""Add consultas_externas table (OSINT Sprint 6)

Revision ID: a1b2c3d4e5f6
Revises: 2597a16c7649
Create Date: 2026-03-20 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "2597a16c7649"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consultas_externas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "inquerito_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inqueritos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo_consulta", sa.String(60), nullable=False),
        sa.Column("documento_hash", sa.String(16), nullable=False),
        sa.Column("custo_estimado", sa.Numeric(10, 4), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("resultado_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_consultas_externas_inquerito_id", "consultas_externas", ["inquerito_id"])
    op.create_index("ix_consultas_externas_created_at", "consultas_externas", ["created_at"])
    op.create_index(
        "ix_consultas_externas_cache",
        "consultas_externas",
        ["inquerito_id", "tipo_consulta", "documento_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_consultas_externas_cache", "consultas_externas")
    op.drop_index("ix_consultas_externas_created_at", "consultas_externas")
    op.drop_index("ix_consultas_externas_inquerito_id", "consultas_externas")
    op.drop_table("consultas_externas")
