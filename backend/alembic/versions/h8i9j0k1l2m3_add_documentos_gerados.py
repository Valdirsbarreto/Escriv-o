"""Add documentos_gerados table

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-05 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documentos_gerados",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("inquerito_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("inqueritos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False, server_default="outro"),
        sa.Column("conteudo", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_documentos_gerados_inquerito_id", "documentos_gerados", ["inquerito_id"])


def downgrade() -> None:
    op.drop_index("ix_documentos_gerados_inquerito_id", "documentos_gerados")
    op.drop_table("documentos_gerados")
