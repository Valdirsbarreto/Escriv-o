"""add ia metadata to documents

Revision ID: e8bab0d91b2a
Revises: j0k1l2m3n4o5
Create Date: 2026-04-12 11:28:35.380804
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'e8bab0d91b2a'
down_revision: Union[str, None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documentos_gerados', sa.Column('modelo_llm', sa.String(length=100), nullable=True))
    op.add_column('documentos_gerados', sa.Column('tokens_prompt', sa.Integer(), nullable=True))
    op.add_column('documentos_gerados', sa.Column('tokens_resposta', sa.Integer(), nullable=True))
    op.add_column('documentos_gerados', sa.Column('custo_estimado', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('documentos_gerados', 'custo_estimado')
    op.drop_column('documentos_gerados', 'tokens_resposta')
    op.drop_column('documentos_gerados', 'tokens_prompt')
    op.drop_column('documentos_gerados', 'modelo_llm')
