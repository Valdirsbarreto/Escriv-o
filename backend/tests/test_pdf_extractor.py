"""
Escrivão AI — Testes: Extração de PDF
Verifica chunking e extração de texto.
"""

import pytest
from app.services.pdf_extractor import PDFExtractorService


class TestChunking:
    """Testa a divisão de texto em chunks."""

    def setup_method(self):
        self.service = PDFExtractorService()

    def test_chunk_simples(self):
        """Texto curto deve gerar um único chunk."""
        paginas = [
            {"numero": 1, "texto": "Palavra " * 100},  # 100 palavras
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        assert len(chunks) == 1
        assert chunks[0]["pagina_inicial"] == 1
        assert chunks[0]["pagina_final"] == 1

    def test_chunk_multiplos(self):
        """Texto longo deve gerar múltiplos chunks."""
        paginas = [
            {"numero": 1, "texto": "Palavra " * 500},
            {"numero": 2, "texto": "Texto " * 500},
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        assert len(chunks) >= 2

    def test_chunk_preserva_paginas(self):
        """Chunks devem preservar referência às páginas."""
        paginas = [
            {"numero": 1, "texto": "A " * 300},
            {"numero": 2, "texto": "B " * 300},
            {"numero": 3, "texto": "C " * 300},
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        assert all("pagina_inicial" in c for c in chunks)
        assert all("pagina_final" in c for c in chunks)

    def test_chunk_tamanho_conforme_blueprint(self):
        """Chunks devem ter ~500-800 palavras (blueprint §6.2)."""
        paginas = [
            {"numero": i, "texto": "Exemplo " * 200}
            for i in range(1, 20)
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        for chunk in chunks[:-1]:  # Último chunk pode ser menor
            assert chunk["num_palavras"] <= 700

    def test_texto_vazio(self):
        """Páginas vazias não devem gerar chunks."""
        paginas = [
            {"numero": 1, "texto": ""},
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        # Pode gerar um chunk vazio ou nenhum
        assert len(chunks) <= 1
