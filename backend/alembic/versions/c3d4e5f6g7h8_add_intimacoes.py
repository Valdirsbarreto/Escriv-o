"""Add intimacoes table (Sprint 7: Google Calendar integration)

Revision ID: c3d4e5f6g7h8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intimacoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "inquerito_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inqueritos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "documento_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documentos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("intimado_nome", sa.String(300), nullable=True),
        sa.Column("intimado_cpf", sa.String(14), nullable=True),
        sa.Column("intimado_qualificacao", sa.String(50), nullable=True),
        sa.Column("numero_inquerito_extraido", sa.String(50), nullable=True),
        sa.Column("data_oitiva", sa.DateTime(), nullable=True),
        sa.Column("local_oitiva", sa.String(300), nullable=True),
        sa.Column("google_event_id", sa.String(200), nullable=True),
        sa.Column("google_event_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="agendada"),
        sa.Column("texto_extraido", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_intimacoes_inquerito_id", "intimacoes", ["inquerito_id"])
    op.create_index("ix_intimacoes_documento_id", "intimacoes", ["documento_id"])
    op.create_index("ix_intimacoes_data_oitiva", "intimacoes", ["data_oitiva"])
    op.create_index("ix_intimacoes_status", "intimacoes", ["status"])


def downgrade() -> None:
    op.drop_index("ix_intimacoes_status", "intimacoes")
    op.drop_index("ix_intimacoes_data_oitiva", "intimacoes")
    op.drop_index("ix_intimacoes_documento_id", "intimacoes")
    op.drop_index("ix_intimacoes_inquerito_id", "intimacoes")
    op.drop_table("intimacoes")
