"""
Escrivão AI — Serviço: Extrator de Intimações
OCR via Gemini Vision + extração LLM de dados estruturados de intimações.
"""

import base64
import json
import logging
from datetime import datetime
from typing import Optional

import google.generativeai as genai

from app.core.config import settings
from app.core.prompts import PROMPT_EXTRACAO_INTIMACAO
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

_GEMINI_OCR_PROMPT = (
    "Você é um OCR especializado em documentos jurídicos brasileiros. "
    "Transcreva fielmente o texto completo desta intimação/documento policial, "
    "preservando nomes, datas, números de inquérito e endereços. "
    "Retorne apenas o texto transcrito, sem comentários."
)


class IntimacaoExtractor:
    """Extrai dados estruturados de intimações a partir de PDF ou imagem."""

    def __init__(self):
        self.llm = LLMService()
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)

    def extrair_texto(self, content: bytes, content_type: str) -> str:
        """
        Extrai texto via Gemini Vision (OCR). Funciona para PDF, PNG, JPG e TIFF.
        Fallback para Tesseract em caso de falha.
        """
        # Gemini aceita PDF diretamente e imagens via inline_data
        try:
            return self._ocr_gemini(content, content_type)
        except Exception as e:
            logger.warning(f"[INTIMACAO] Gemini Vision falhou, tentando Tesseract: {e}")
            return self._ocr_tesseract_fallback(content, content_type)

    def _ocr_gemini(self, content: bytes, content_type: str) -> str:
        """OCR via Gemini Vision (gemini-2.0-flash)."""
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Gemini aceita PDFs e imagens como inline_data
        mime = content_type if content_type else "application/pdf"
        if mime in ("image/jpg",):
            mime = "image/jpeg"

        part = {"inline_data": {"mime_type": mime, "data": base64.b64encode(content).decode()}}
        response = model.generate_content([_GEMINI_OCR_PROMPT, part])
        texto = response.text.strip()
        logger.info(f"[INTIMACAO] Gemini Vision extraiu {len(texto)} chars")
        return texto

    def _ocr_tesseract_fallback(self, content: bytes, content_type: str) -> str:
        """Fallback: Tesseract para imagens ou extração nativa para PDFs."""
        is_image = content_type in ("image/png", "image/jpeg", "image/jpg", "image/tiff")
        if is_image:
            try:
                import pytesseract
                from PIL import Image
                import io as _io
                img = Image.open(_io.BytesIO(content))
                return pytesseract.image_to_string(img, lang="por", config="--psm 6").strip()
            except Exception as e:
                logger.error(f"[INTIMACAO] Tesseract falhou: {e}")
                return ""

        from app.services.pdf_extractor import PDFExtractorService
        pdf_svc = PDFExtractorService()
        resultado = pdf_svc.extract_text(content)
        paginas = resultado.get("paginas", [])
        paginas_ocr = [p["numero"] for p in paginas if p.get("precisa_ocr")]
        if paginas_ocr:
            textos_ocr = pdf_svc.apply_ocr(content, paginas_ocr)
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
