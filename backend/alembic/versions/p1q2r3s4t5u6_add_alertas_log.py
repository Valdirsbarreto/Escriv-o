"""add_alertas_log

Revision ID: p1q2r3s4t5u6
Revises: o5p6q7r8s9t0
Create Date: 2026-04-21

Cria tabela alertas_log para persistir alertas do sistema (painel in-app).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "p1q2r3s4t5u6"
down_revision = "o5p6q7r8s9t0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alertas_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("nivel", sa.String(10), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("mensagem_html", sa.Text(), nullable=False),
        sa.Column("identificador", sa.String(200), nullable=True),
        sa.Column("lido", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_alertas_log_tipo", "alertas_log", ["tipo"])
    op.create_index("ix_alertas_log_created_at", "alertas_log", ["created_at"])
    op.create_index("ix_alertas_log_lido", "alertas_log", ["lido"])


def downgrade() -> None:
    op.drop_index("ix_alertas_log_lido", table_name="alertas_log")
    op.drop_index("ix_alertas_log_created_at", table_name="alertas_log")
    op.drop_index("ix_alertas_log_tipo", table_name="alertas_log")
    op.drop_table("alertas_log")
