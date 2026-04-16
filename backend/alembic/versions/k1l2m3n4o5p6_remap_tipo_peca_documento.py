"""remap_tipo_peca_documento

Revision ID: k1l2m3n4o5p6
Revises: e8bab0d91b2a
Create Date: 2026-04-15

Atualiza documento.tipo_peca e pecas_extraidas.tipo para a nova taxonomia
(classifier v2 — 30+ tipos, alinhada com PRIORIDADE_TIPO dos workers).

Mapeamento:
  laudo              → laudo_pericial
  oficio             → oficio_expedido          (conservador — sem re-leitura)
  bo / boletim       → boletim_ocorrencia
  relatorio_final    → relatorio_policial
  relatorio          → informacao_investigacao
  extrato_bancario   → extrato_financeiro
  termo_oitiva       → termo_depoimento
  termo_declaracao_vitima    → termo_declaracao
  termo_oitiva_testemunha    → termo_depoimento
  termo_oitiva_testemunha2   → termo_depoimento
"""
from alembic import op

revision = 'k1l2m3n4o5p6'
down_revision = 'e8bab0d91b2a'
branch_labels = None
depends_on = None

# Tabelas que armazenam tipo_peca / tipo
_TABLES = {
    "documentos": "tipo_peca",
    "pecas_extraidas": "tipo",
}

_REMAP = [
    ("laudo",                   "laudo_pericial"),
    ("oficio",                  "oficio_expedido"),
    ("bo",                      "boletim_ocorrencia"),
    ("boletim",                 "boletim_ocorrencia"),
    ("relatorio_final",         "relatorio_policial"),
    ("relatorio",               "informacao_investigacao"),
    ("extrato_bancario",        "extrato_financeiro"),
    ("termo_oitiva",            "termo_depoimento"),
    ("termo_declaracao_vitima", "termo_declaracao"),
    ("termo_oitiva_testemunha", "termo_depoimento"),
]


def upgrade() -> None:
    for tabela, coluna in _TABLES.items():
        for antigo, novo in _REMAP:
            op.execute(
                f"UPDATE {tabela} SET {coluna} = '{novo}' WHERE {coluna} = '{antigo}'"
            )


def downgrade() -> None:
    for tabela, coluna in _TABLES.items():
        for antigo, novo in _REMAP:
            op.execute(
                f"UPDATE {tabela} SET {coluna} = '{antigo}' WHERE {coluna} = '{novo}'"
            )
