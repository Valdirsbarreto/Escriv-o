"""
Escrivão AI — Agente: Análise de Extratos Bancários
Processa texto de extratos e extrai transações, contrapartes e alertas em JSON.
Conforme blueprint §9.3 (Agente de Extratos).
"""

import json
import logging
import uuid
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import LLMService
from app.core.prompts import PROMPT_ANALISE_EXTRATO
from app.models.documento import Documento
from app.models.resultado_agente import ResultadoAgente

logger = logging.getLogger(__name__)

# Limite para extratos muito longos (evitar estourar contexto do LLM)
MAX_CHARS_EXTRATO = 40_000


class AgenteExtrato:
    """
    Analisa extratos bancários extraídos de PDFs e retorna estrutura JSON
    com transações, contrapartes, padrões suspeitos e score de suspeição.
    """

    def __init__(self):
        self.llm = LLMService()

    async def analisar_extrato(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        documento_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Analisa o texto extraído de um documento de extrato bancário.

        Returns:
            JSON estruturado com transações, saldos, contrapartes e alertas.
        """
        # Buscar texto do documento
        doc = await db.get(Documento, documento_id)
        if not doc:
            raise ValueError(f"Documento {documento_id} não encontrado")

        if not doc.texto_extraido:
            raise ValueError(f"Documento {documento_id} não possui texto extraído")

        texto_extrato = doc.texto_extraido[:MAX_CHARS_EXTRATO]

        prompt = PROMPT_ANALISE_EXTRATO.format(texto_extrato=texto_extrato)

        try:
            result = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="standard",
                temperature=0.1,
                max_tokens=4000,
                json_mode=True,
            )

            content = result["content"].strip()
            analise_json = json.loads(content)

            # Garantir estrutura mínima
            analise_json.setdefault("transacoes", [])
            analise_json.setdefault("alertas", [])
            analise_json.setdefault("contrapartes_frequentes", [])
            analise_json.setdefault("score_suspeicao", 0)

            # Persistir resultado
            registro = ResultadoAgente(
                inquerito_id=inquerito_id,
                tipo_agente="extrato",
                referencia_id=documento_id,
                resultado_json=analise_json,
                modelo_llm=result.get("model"),
            )
            db.add(registro)
            await db.commit()

            n_transacoes = len(analise_json.get("transacoes", []))
            score = analise_json.get("score_suspeicao", 0)
            logger.info(
                f"[AGENTE-EXTRATO] Analisado doc {documento_id}: "
                f"{n_transacoes} transações, score={score}"
            )
            return analise_json

        except json.JSONDecodeError as e:
            logger.error(f"[AGENTE-EXTRATO] JSON inválido: {e}")
            raise
        except Exception as e:
            logger.error(f"[AGENTE-EXTRATO] Erro: {e}")
            raise

    async def obter_analise_anterior(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        documento_id: uuid.UUID,
    ) -> Dict[str, Any] | None:
        """Retorna análise anterior do cache se existir."""
        from sqlalchemy import select
        result = await db.execute(
            select(ResultadoAgente)
            .where(ResultadoAgente.inquerito_id == inquerito_id)
            .where(ResultadoAgente.tipo_agente == "extrato")
            .where(ResultadoAgente.referencia_id == documento_id)
        )
        registro = result.scalar_one_or_none()
        return registro.resultado_json if registro else None
