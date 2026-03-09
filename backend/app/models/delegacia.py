"""
Escrivão AI — Modelo: Delegacia
Tabela de referência com o portfólio de delegacias da PC/RJ.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Delegacia(Base):
    __tablename__ = "delegacias"

    codigo: Mapped[str] = mapped_column(String(3), primary_key=True)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str | None] = mapped_column(Text, nullable=True)
    municipio: Mapped[str | None] = mapped_column(Text, nullable=True)
    departamento: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Delegacia {self.codigo} - {self.nome}>"
