"""billing_source_and_usage_events

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-04-16

Adiciona rastreabilidade de origem aos custos externos e cria
tabela de eventos de uso para telemetria interna (Serper, etc.).

Mudanças:
  custos_externos: + source (manual|official_api|estimated|internal_telemetry)
                   + confidence (high|medium|low)
                   + raw_payload (JSONB)
  usage_events: nova tabela (provider, metric, quantity, cost_estimate_usd, occurred_at, meta)
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'n4o5p6q7r8s9'
down_revision = 'm3n4o5p6q7r8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Parte A: custos_externos ─────────────────────────────────────────────
    op.add_column(
        "custos_externos",
        sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
    )
    op.add_column(
        "custos_externos",
        sa.Column("confidence", sa.String(10), nullable=False, server_default="high"),
    )
    op.add_column(
        "custos_externos",
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # ── Parte B: usage_events ────────────────────────────────────────────────
    op.create_table(
        "usage_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(40), nullable=False),       # "serper", "directdata"
        sa.Column("metric", sa.String(60), nullable=False),          # "search_query"
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("cost_estimate_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_usage_events_provider_occurred",
        "usage_events",
        ["provider", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_events_provider_occurred", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_column("custos_externos", "raw_payload")
    op.drop_column("custos_externos", "confidence")
    op.drop_column("custos_externos", "source")
