"""add_oitivas

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-04-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'r2s3t4u5v6w7'
down_revision = 'q1r2s3t4u5v6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'oitivas',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('inquerito_id', UUID(as_uuid=True), sa.ForeignKey('inqueritos.id'), nullable=False),
        sa.Column('pessoa_id', UUID(as_uuid=True), sa.ForeignKey('pessoas.id'), nullable=True),
        sa.Column('audio_url', sa.String(500), nullable=True),
        sa.Column('transcricao_bruta', sa.Text, nullable=True),
        sa.Column('termo_com_timestamps', sa.Text, nullable=True),
        sa.Column('termo_limpo', sa.Text, nullable=True),
        sa.Column('duracao_segundos', sa.Integer, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='rascunho'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_oitivas_inquerito_id', 'oitivas', ['inquerito_id'])
    op.create_index('ix_oitivas_pessoa_id', 'oitivas', ['pessoa_id'])


def downgrade() -> None:
    op.drop_table('oitivas')
