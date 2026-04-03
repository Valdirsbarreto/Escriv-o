"""
Escrivão AI — Serviço: Extrator de Intimações
Gemini Vision extrai texto E dados estruturados em uma única chamada.
Fallback: OCR Tesseract para extração de texto.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from google import genai
from google.genai import types as genai_types

from app.core.config import settings

logger = logging.getLogger(__name__)

_PROMPT_EXTRACAO_DIRETA = """Você é um extrator especializado em intimações policiais brasileiras.

Analise este documento e retorne APENAS um objeto JSON com os campos abaixo.

Campos:
- intimado_nome: nome completo da pessoa intimada (string ou null)
- intimado_cpf: CPF apenas dígitos ou formato XXX.XXX.XXX-XX (string ou null)
- intimado_qualificacao: "testemunha", "investigado", "vitima", "perito" ou "outro" (string ou null)
- numero_inquerito: número do IP no formato DDD-NNNNNN/AAAA ou similar (string ou null)
- data_oitiva: data/hora em ISO 8601 YYYY-MM-DDTHH:MM:00 — se só houver data use T09:00:00 (string ou null)
- local_oitiva: endereço ou local da oitiva (string ou null)
- texto_completo: transcrição fiel do documento completo (string)

Regras:
1. Não invente dados. Campo ausente = null.
2. Para datas em português (ex: "15 de março de 2026 às 14h30") converta para ISO 8601.
3. Retorne SOMENTE o JSON, sem markdown ou explicações.
"""

_PROMPT_OCR_ONLY = (
    "Você é um OCR especializado em documentos jurídicos brasileiros. "
    "Transcreva fielmente o texto completo desta intimação/documento policial, "
    "preservando nomes, datas, números de inquérito e endereços. "
    "Retorne apenas o texto transcrito, sem comentários."
)


class IntimacaoExtractor:
    """
    Extrai texto e dados estruturados de intimações via Gemini Vision.
    Uma única chamada faz OCR + extração de campos em JSON.
    """

    def __init__(self):
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    def _mime(self, content_type: str) -> str:
        if content_type in ("image/jpg",):
            return "image/jpeg"
        return content_type or "application/pdf"

    def _part(self, content: bytes, content_type: str):
        return genai_types.Part.from_bytes(data=content, mime_type=self._mime(content_type))

    def _ocr_tesseract_fallback(self, content: bytes, content_type: str) -> str:
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
        return "\n\n".join(p["texto"] for p in paginas if p.get("texto"))

    async def extrair_tudo(self, content: bytes, content_type: str) -> tuple[str, dict]:
        """
        Chama Gemini Vision UMA VEZ e retorna (texto_completo, dados_estruturados).
        Executa o SDK síncrono em thread separada para não bloquear o event loop.
        """
        try:
            part = self._part(content, content_type)
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model="gemini-2.0-flash-001",
                contents=[_PROMPT_EXTRACAO_DIRETA, part],
            )
            raw = response.text.strip()

            # Remove markdown se presente
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            dados_raw = json.loads(raw)
            texto = dados_raw.pop("texto_completo", "") or ""
            logger.info(f"[INTIMACAO] Gemini Vision extraiu texto ({len(texto)} chars) + dados estruturados")
            return texto, dados_raw

        except Exception as e:
            logger.error(f"[INTIMACAO] extrair_tudo falhou: {e} — usando fallback")
            return "", {}

    async def extrair_dados(self, texto: str) -> dict:
        """
        Fallback: extrai dados de texto já transcrito via Gemini (sem Vision).
        Usado quando extrair_tudo não retornou dados suficientes.
        """
        from app.core.prompts import PROMPT_EXTRACAO_INTIMACAO
        try:
            prompt = PROMPT_EXTRACAO_INTIMACAO.format(texto=texto[:4000])
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model="gemini-2.0-flash-001",
                contents=prompt,
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            dados = json.loads(raw.strip())
        except Exception as e:
            logger.warning(f"[INTIMACAO] extrair_dados fallback falhou: {e}")
            dados = {}

        return self._normalizar_dados(dados)

    def _normalizar_dados(self, dados: dict) -> dict:
        data_oitiva: Optional[datetime] = None
        data_str = dados.get("data_oitiva")
        if data_str:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
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
