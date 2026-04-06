"""Add pecas_extraidas table

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-04-06 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pecas_extraidas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "inquerito_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inqueritos.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "documento_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documentos.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("tipo", sa.String(80), nullable=False, server_default="outro"),
        sa.Column("conteudo_texto", sa.Text, nullable=False),
        sa.Column("pagina_inicial", sa.Integer, nullable=True),
        sa.Column("pagina_final", sa.Integer, nullable=True),
        sa.Column("resumo", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_pecas_extraidas_inquerito_id", "pecas_extraidas", ["inquerito_id"])
    op.create_index("ix_pecas_extraidas_documento_id", "pecas_extraidas", ["documento_id"])


def downgrade() -> None:
    op.drop_index("ix_pecas_extraidas_documento_id", "pecas_extraidas")
    op.drop_index("ix_pecas_extraidas_inquerito_id", "pecas_extraidas")
    op.drop_table("pecas_extraidas")
