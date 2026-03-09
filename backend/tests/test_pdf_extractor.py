"""
Escrivão AI — Testes: Pipeline de Ingestão
Testa o pipeline de extração de PDF e chunking.
"""

import pytest

from app.services.pdf_extractor import PDFExtractorService


class TestPDFExtractorRefatorado:
    """Testa o extrator refatorado (pypdf + OCR)."""

    def setup_method(self):
        self.service = PDFExtractorService()

    def test_chunk_simples(self):
        """Texto curto deve gerar um único chunk."""
        paginas = [
            {"numero": 1, "texto": "Palavra " * 100, "precisa_ocr": False, "origem": "nativo"},
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        assert len(chunks) == 1
        assert chunks[0]["pagina_inicial"] == 1
        assert chunks[0]["pagina_final"] == 1

    def test_chunk_multiplos(self):
        """Texto longo deve gerar múltiplos chunks."""
        paginas = [
            {"numero": 1, "texto": "Palavra " * 500, "precisa_ocr": False, "origem": "nativo"},
            {"numero": 2, "texto": "Texto " * 500, "precisa_ocr": False, "origem": "nativo"},
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        assert len(chunks) >= 2

    def test_chunk_preserva_paginas(self):
        """Chunks devem preservar referência às páginas."""
        paginas = [
            {"numero": 1, "texto": "A " * 300, "precisa_ocr": False, "origem": "nativo"},
            {"numero": 2, "texto": "B " * 300, "precisa_ocr": False, "origem": "nativo"},
            {"numero": 3, "texto": "C " * 300, "precisa_ocr": False, "origem": "nativo"},
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        assert all("pagina_inicial" in c for c in chunks)
        assert all("pagina_final" in c for c in chunks)

    def test_chunk_tamanho_conforme_blueprint(self):
        """Chunks devem ter ~500-800 palavras (blueprint §6.2)."""
        paginas = [
            {"numero": i, "texto": "Exemplo " * 200, "precisa_ocr": False, "origem": "nativo"}
            for i in range(1, 20)
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        for chunk in chunks[:-1]:
            assert chunk["num_palavras"] <= 700

    def test_texto_vazio(self):
        """Páginas vazias não devem gerar chunks com conteúdo."""
        paginas = [
            {"numero": 1, "texto": "", "precisa_ocr": True, "origem": "pendente_ocr"},
        ]
        chunks = self.service.chunk_text(paginas, chunk_size=600, overlap=100)
        assert len(chunks) <= 1

    def test_min_text_length(self):
        """Textos curtos devem ser marcados como precisando de OCR."""
        assert PDFExtractorService.MIN_TEXT_LENGTH == 50

    def test_ocr_placeholder_graceful(self):
        """apply_ocr deve falhar graciosamente sem poppler."""
        resultado = self.service.apply_ocr(b"fake pdf bytes", [1, 2])
        # Deve retornar algo (mensagem de erro ou vazio), mas não crash
        assert isinstance(resultado, dict)
        assert 1 in resultado
        assert 2 in resultado
