"""recalcular_custo_modelos_antigos

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-04-16

Recalcula custo_usd e custo_brl nos registros de consumo_api onde o modelo
não estava mapeado em _estimar_custo e caiu no fallback $1.00/$3.00/1M tokens.

Modelos afetados:
  gemini-pro-latest  → in $0.50 / out $1.50 por 1M tokens
  gemini-flash-latest → in $0.075 / out $0.30 por 1M tokens
  llama-3.3-70b*     → in $0.59  / out $0.79 por 1M tokens
  llama-3.1-8b*      → in $0.05  / out $0.08 por 1M tokens
  llama (genérico)   → in $0.20  / out $0.30 por 1M tokens

A cotacao_dolar usada na recalculação vem do próprio registro (campo cotacao_dolar),
preservando o câmbio histórico.
"""
from alembic import op
from sqlalchemy import text

revision = 'm3n4o5p6q7r8'
down_revision = 'l2m3n4o5p6q7'
branch_labels = None
depends_on = None

# (modelo_substring, in_per_1M_usd, out_per_1M_usd)
REMAP = [
    ("gemini-pro-latest",   0.50,  1.50),
    ("gemini-flash-latest", 0.075, 0.30),
    ("gemini-pro",          0.50,  1.50),   # alias sem versão
    ("llama-3.3-70b",       0.59,  0.79),
    ("llama-3.1-70b",       0.59,  0.79),
    ("llama-3.1-8b",        0.05,  0.08),
    ("llama",               0.20,  0.30),   # fallback llama genérico
]


def upgrade() -> None:
    conn = op.get_bind()
    for substring, price_in, price_out in REMAP:
        conn.execute(text("""
            UPDATE consumo_api
            SET
                custo_usd = (tokens_prompt * :pin + tokens_saida * :pout) / 1000000.0,
                custo_brl = (tokens_prompt * :pin + tokens_saida * :pout) / 1000000.0
                            * COALESCE(cotacao_dolar, 5.80)
            WHERE LOWER(modelo) LIKE :pat
        """), {
            "pin":  price_in,
            "pout": price_out,
            "pat":  f"%{substring}%",
        })


def downgrade() -> None:
    # Não é possível reverter sem os valores originais — operação destrutiva intencional.
    pass
