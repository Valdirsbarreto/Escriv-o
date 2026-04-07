"""
Escrivão AI — Serviço de Extração de PDF
Extrai texto nativo de PDFs com pypdf + OCR seletivo com pytesseract.
"""

import io
import logging
from typing import List, Dict, Optional

from pypdf import PdfReader

logger = logging.getLogger(__name__)


class PDFExtractorService:
    """Extrai texto de arquivos PDF com OCR seletivo."""

    MIN_TEXT_LENGTH = 50  # Abaixo disso, considerar OCR
    MIN_LETTER_RATIO = 0.40  # Abaixo de 40% de letras → texto corrompido → OCR

    @staticmethod
    def _texto_legivel(texto: str) -> bool:
        """
        Verifica se o texto nativo é legível.
        Textos de PDFs mal-codificados têm alta proporção de não-letras (símbolos, dígitos isolados).
        """
        if not texto:
            return False
        letras = sum(1 for c in texto if c.isalpha())
        ratio = letras / len(texto)
        return ratio >= PDFExtractorService.MIN_LETTER_RATIO

    def extract_text(self, content: bytes) -> Dict:
        """
        Extrai texto de todas as páginas de um PDF.

        Retorna:
        {
            "total_paginas": int,
            "paginas": [
                {"numero": int, "texto": str, "precisa_ocr": bool, "origem": str}
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
            # Precisa OCR se: muito curto OU texto corrompido (baixo ratio de letras)
            precisa_ocr = len(texto) < self.MIN_TEXT_LENGTH or not self._texto_legivel(texto)

            paginas.append({
                "numero": i,
                "texto": texto,
                "precisa_ocr": precisa_ocr,
                "origem": "nativo" if not precisa_ocr else "pendente_ocr",
            })
            textos.append(texto)

        return {
            "total_paginas": len(reader.pages),
            "paginas": paginas,
            "texto_completo": "\n\n".join(textos),
        }

    def apply_ocr(
        self,
        pdf_content: bytes,
        page_numbers: List[int],
        dpi: int = 200,
    ) -> Dict[int, str]:
        """
        Aplica OCR seletivo nas páginas especificadas.
        Usa pdf2image para converter PDF→imagem, depois pytesseract.

        Args:
            pdf_content: bytes do PDF
            page_numbers: lista de números de página (1-indexed)
            dpi: resolução para conversão (200 é bom balanço qualidade/velocidade)

        Returns:
            Dict mapeando número da página → texto extraído via OCR
        """
        resultados = {}

        try:
            from pdf2image import convert_from_bytes
            import pytesseract
        except ImportError as e:
            logger.warning(f"[OCR] Dependências de OCR não disponíveis: {e}")
            return {p: "[OCR não disponível - instale pytesseract e poppler]" for p in page_numbers}

        for page_num in page_numbers:
            try:
                # Converte apenas a página específica
                images = convert_from_bytes(
                    pdf_content,
                    first_page=page_num,
                    last_page=page_num,
                    dpi=dpi,
                )

                if images:
                    # OCR com idioma pt-br (requer tessdata 'por')
                    texto = pytesseract.image_to_string(
                        images[0],
                        lang="por",
                        config="--psm 6",  # Assume bloco uniforme de texto
                    )
                    texto = texto.strip()
                    resultados[page_num] = texto
                    logger.info(
                        f"[OCR] Página {page_num}: {len(texto)} chars extraídos"
                    )
                else:
                    resultados[page_num] = ""

            except Exception as e:
                logger.error(f"[OCR] Erro na página {page_num}: {e}")
                resultados[page_num] = f"[Erro OCR: {str(e)[:100]}]"

        return resultados

    def extract_with_ocr(self, content: bytes, force_ocr: bool = False) -> Dict:
        """
        Extração completa: texto nativo + OCR seletivo onde necessário.
        Pipeline completo conforme blueprint §6.1.

        Args:
            content: bytes do PDF
            force_ocr: se True, aplica OCR em todas as páginas

        Returns:
            Mesmo formato de extract_text(), com páginas OCR já preenchidas
        """
        # 1. Extração nativa
        result = self.extract_text(content)

        # 2. Identificar páginas para OCR
        if force_ocr:
            paginas_ocr = [p["numero"] for p in result["paginas"]]
        else:
            paginas_ocr = [
                p["numero"] for p in result["paginas"] if p["precisa_ocr"]
            ]

        if not paginas_ocr:
            logger.info("[OCR] Nenhuma página precisa de OCR")
            return result

        logger.info(f"[OCR] Aplicando OCR em {len(paginas_ocr)} páginas: {paginas_ocr}")

        # 3. Aplicar OCR seletivo
        ocr_results = self.apply_ocr(content, paginas_ocr)

        # 4. Mesclar resultados
        textos = []
        for pagina in result["paginas"]:
            if pagina["numero"] in ocr_results:
                ocr_text = ocr_results[pagina["numero"]]
                if len(ocr_text) > len(pagina["texto"]):
                    pagina["texto"] = ocr_text
                    pagina["origem"] = "ocr"
                    pagina["precisa_ocr"] = False
            textos.append(pagina["texto"])

        result["texto_completo"] = "\n\n".join(textos)
        return result

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

    def extract_image(self, content: bytes) -> Dict:
        """
        Aplica OCR direto em arquivos de imagem (TIFF, PNG, JPG).
        Retorna no mesmo formato de extract_with_ocr(), assumindo página única (1).
        """
        try:
            from PIL import Image
            import pytesseract
        except ImportError as e:
            logger.warning(f"[OCR] Dependências de OCR para imagem não disponíveis: {e}")
            texto = "[OCR não disponível - instale pytesseract e PIL]"
            paginas = [{"numero": 1, "texto": texto, "precisa_ocr": False, "origem": "erro"}]
            return {"total_paginas": 1, "paginas": paginas, "texto_completo": texto}

        try:
            img = Image.open(io.BytesIO(content))
            texto = pytesseract.image_to_string(
                img,
                lang="por",
                config="--psm 6",
            )
            texto = texto.strip()
            logger.info(f"[OCR-IMG] Imagem formatada: {len(texto)} chars extraídos")
            paginas = [{"numero": 1, "texto": texto, "precisa_ocr": False, "origem": "ocr"}]
            return {"total_paginas": 1, "paginas": paginas, "texto_completo": texto}
        except Exception as e:
            logger.error(f"[OCR-IMG] Erro ao extrair de imagem: {e}")
            texto = f"[Erro OCR: {str(e)[:100]}]"
            paginas = [{"numero": 1, "texto": texto, "precisa_ocr": False, "origem": "erro"}]
            return {"total_paginas": 1, "paginas": paginas, "texto_completo": texto}

    def extract_any_file(self, content: bytes, content_type: str) -> Dict:
        """
        Ponto de entrada unificado: direciona para OCR de imagem ou extração de PDF
        de acordo com o content_type (MIME type).
        Retorna dicionário contendo paginas e texto_completo.
        """
        mime_lower = content_type.lower()
        if mime_lower in ["image/tiff", "image/png", "image/jpeg", "image/jpg"]:
            logger.info(f"[EXTRACT-ANY] Format detectado como imagem ({mime_lower}). Roteando para extract_image.")
            return self.extract_image(content)
        elif mime_lower == "application/pdf":
            logger.info("[EXTRACT-ANY] Formato detectado como PDF. Roteando para extract_with_ocr.")
            return self.extract_with_ocr(content)
        else:
            logger.warning(f"[EXTRACT-ANY] Tipo não suportado: {mime_lower}, assumindo PDF.")
            return self.extract_with_ocr(content)
