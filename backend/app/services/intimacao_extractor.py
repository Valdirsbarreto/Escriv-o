"""
Escrivão AI — Serviço: Extrator de Intimações
Combina OCR (pdf_extractor) + LLM para extrair dados estruturados de intimações.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from app.core.prompts import PROMPT_EXTRACAO_INTIMACAO
from app.services.llm_service import LLMService
from app.services.pdf_extractor import PDFExtractorService

logger = logging.getLogger(__name__)


class IntimacaoExtractor:
    """Extrai dados estruturados de intimações a partir de PDF ou imagem."""

    def __init__(self):
        self.pdf_extractor = PDFExtractorService()
        self.llm = LLMService()

    def extrair_texto(self, content: bytes, content_type: str) -> str:
        """
        Extrai texto bruto de PDF ou imagem.
        Retorna o texto concatenado de todas as páginas.
        """
        is_image = content_type in ("image/png", "image/jpeg", "image/jpg", "image/tiff")

        if is_image:
            try:
                import pytesseract
                from PIL import Image
                import io as _io
                img = Image.open(_io.BytesIO(content))
                texto = pytesseract.image_to_string(img, lang="por", config="--psm 6")
                return texto.strip()
            except Exception as e:
                logger.error(f"[INTIMACAO] OCR de imagem falhou: {e}")
                return ""

        # PDF: tenta extração nativa, usa OCR nas páginas que precisam
        resultado = self.pdf_extractor.extract_text(content)
        paginas = resultado.get("paginas", [])

        # OCR nas páginas com pouco texto nativo
        paginas_ocr = [p["numero"] for p in paginas if p.get("precisa_ocr")]
        if paginas_ocr:
            textos_ocr = self.pdf_extractor.apply_ocr(content, paginas_ocr)
            for p in paginas:
                if p["numero"] in textos_ocr:
                    p["texto"] = textos_ocr[p["numero"]]

        return "\n\n".join(p["texto"] for p in paginas if p.get("texto"))

    async def extrair_dados(self, texto: str) -> dict:
        """
        Usa LLM (tier econômico) para extrair campos estruturados da intimação.

        Retorna:
        {
            "intimado_nome": str | None,
            "intimado_cpf": str | None,
            "intimado_qualificacao": str | None,
            "numero_inquerito": str | None,
            "data_oitiva": datetime | None,
            "local_oitiva": str | None,
        }
        """
        prompt = PROMPT_EXTRACAO_INTIMACAO.format(texto=texto[:4000])

        resposta = await self.llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="economico",
            temperature=0.0,
            max_tokens=500,
            json_mode=True,
        )

        raw = resposta.get("content", "").strip()

        # Remove markdown code fences se presentes
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            dados = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"[INTIMACAO] LLM retornou JSON inválido: {raw[:200]}")
            dados = {}

        # Converte data_oitiva string → datetime
        data_oitiva: Optional[datetime] = None
        data_str = dados.get("data_oitiva")
        if data_str:
            for fmt in (
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d",
            ):
                try:
                    data_oitiva = datetime.strptime(data_str, fmt)
                    break
                except ValueError:
                    continue
            if not data_oitiva:
                logger.warning(f"[INTIMACAO] Não foi possível parsear data: {data_str}")

        return {
            "intimado_nome": dados.get("intimado_nome"),
            "intimado_cpf": dados.get("intimado_cpf"),
            "intimado_qualificacao": dados.get("intimado_qualificacao"),
            "numero_inquerito": dados.get("numero_inquerito"),
            "data_oitiva": data_oitiva,
            "local_oitiva": dados.get("local_oitiva"),
        }
