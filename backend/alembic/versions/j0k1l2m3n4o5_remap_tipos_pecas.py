"""remap_tipos_pecas

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-04-12

Remapeia tipos antigos de peças para a nova taxonomia de 23 tipos.
"""
from alembic import op

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Renomeações diretas e seguras
    op.execute("UPDATE pecas_extraidas SET tipo = 'laudo_pericial' WHERE tipo = 'laudo'")
    op.execute("UPDATE pecas_extraidas SET tipo = 'oficio_expedido' WHERE tipo = 'oficio'")
    op.execute("UPDATE pecas_extraidas SET tipo = 'termo_depoimento' WHERE tipo = 'termo_oitiva'")
    # 'bo', 'portaria', 'despacho', 'requisicao', 'mandado',
    # 'auto_apreensao', 'termo_declaracao', 'outro' — mantidos como estão


def downgrade() -> None:
    op.execute("UPDATE pecas_extraidas SET tipo = 'laudo' WHERE tipo = 'laudo_pericial'")
    op.execute("UPDATE pecas_extraidas SET tipo = 'oficio' WHERE tipo = 'oficio_expedido'")
    op.execute("UPDATE pecas_extraidas SET tipo = 'termo_oitiva' WHERE tipo = 'termo_depoimento'")
