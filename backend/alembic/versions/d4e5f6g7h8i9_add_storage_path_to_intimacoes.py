"""Add storage_path to intimacoes + make documentos.inquerito_id nullable

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-03-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adiciona storage_path na tabela intimacoes (para uploads sem inquérito vinculado)
    op.add_column("intimacoes", sa.Column("storage_path", sa.String(1000), nullable=True))

    # Torna documentos.inquerito_id nullable (intimações podem não ter inquérito ainda)
    op.alter_column("documentos", "inquerito_id", nullable=True)


def downgrade() -> None:
    op.alter_column("documentos", "inquerito_id", nullable=False)
    op.drop_column("intimacoes", "storage_path")
