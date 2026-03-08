"""
Escrivão AI — Serviço de Extração de PDF
Extrai texto nativo de PDFs com PyPDF2. Placeholder para OCR futuro.
"""

import io
from typing import List, Dict

from PyPDF2 import PdfReader


class PDFExtractorService:
    """Extrai texto de arquivos PDF, página por página."""

    MIN_TEXT_LENGTH = 50  # Abaixo disso, considerar OCR

    def extract_text(self, content: bytes) -> Dict:
        """
        Extrai texto de todas as páginas de um PDF.

        Retorna:
        {
            "total_paginas": int,
            "paginas": [
                {"numero": int, "texto": str, "precisa_ocr": bool}
            ],
            "texto_completo": str
        }
        """
        reader = PdfReader(io.BytesIO(content))
        paginas = []
        textos = []

        for i, page in enumerate(reader.pages, start=1):
            texto = page.extract_text() or ""
            texto = texto.strip()
            precisa_ocr = len(texto) < self.MIN_TEXT_LENGTH

            paginas.append({
                "numero": i,
                "texto": texto,
                "precisa_ocr": precisa_ocr,
            })
            textos.append(texto)

        return {
            "total_paginas": len(reader.pages),
            "paginas": paginas,
            "texto_completo": "\n\n".join(textos),
        }

    def chunk_text(
        self,
        paginas: List[Dict],
        chunk_size: int = 600,
        overlap: int = 100,
    ) -> List[Dict]:
        """
        Divide o texto extraído em chunks de ~chunk_size palavras
        com overlap para manter contexto.

        Cada chunk preserva metadados de página inicial/final.
        Conforme blueprint §6.2: chunks de 500-800 palavras.
        """
        chunks = []
        current_words = []
        current_page_start = 1
        current_page_end = 1

        for pagina in paginas:
            words = pagina["texto"].split()
            page_num = pagina["numero"]

            if not current_words:
                current_page_start = page_num

            current_words.extend(words)
            current_page_end = page_num

            while len(current_words) >= chunk_size:
                chunk_words = current_words[:chunk_size]
                chunks.append({
                    "texto": " ".join(chunk_words),
                    "pagina_inicial": current_page_start,
                    "pagina_final": current_page_end,
                    "num_palavras": len(chunk_words),
                })

                # Manter overlap
                current_words = current_words[chunk_size - overlap:]
                current_page_start = current_page_end

        # Chunk residual
        if current_words:
            chunks.append({
                "texto": " ".join(current_words),
                "pagina_inicial": current_page_start,
                "pagina_final": current_page_end,
                "num_palavras": len(current_words),
            })

        return chunks

    @staticmethod
    def apply_ocr(content: bytes, page_numbers: List[int]) -> Dict[int, str]:
        """
        Placeholder para OCR seletivo.
        Será implementado no Sprint 2 com Tesseract ou alternativa.
        """
        # TODO: Implementar OCR seletivo (Sprint 2)
        return {page: "[OCR pendente]" for page in page_numbers}
