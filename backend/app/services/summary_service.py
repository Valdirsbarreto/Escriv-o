"""
Escrivão AI — Serviço de Resumos Hierárquicos
Gera e faz cache de resumos em 4 níveis: pagina, documento, volume, caso.
Conforme blueprint §6.4 (Resumos Hierárquicos).
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.llm_service import LLMService
from app.core.prompts import (
    PROMPT_RESUMO_PAGINA,
    PROMPT_RESUMO_DOCUMENTO,
    PROMPT_RESUMO_VOLUME,
    PROMPT_RESUMO_CASO,
)
from app.models.resumo_cache import ResumoCache

logger = logging.getLogger(__name__)

# Limites de texto por nível — ampliados para aproveitar janela de 1M tokens do gemini-1.5-flash-8b
MAX_CHARS_PAGINA    =  5_000
MAX_CHARS_DOCUMENTO = 50_000   # era 25_000
MAX_CHARS_VOLUME    = 40_000   # era 20_000 — composto de resumos de docs
MAX_CHARS_CASO      = 30_000   # era 15_000 — composto de resumos de volumes


class SummaryService:
    """
    Gera e armazena em cache resumos hierárquicos via LLM Econômico.
    Verifica o cache antes de cada chamada ao LLM para evitar reprocessamento.
    """

    def __init__(self):
        self.llm = LLMService()

    # ── Cache helpers ─────────────────────────────────────────────────────────

    async def _buscar_cache(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        nivel: str,
        referencia_id: Optional[uuid.UUID] = None,
    ) -> Optional[str]:
        """Retorna o texto resumido do cache se existir, caso contrário None."""
        result = await db.execute(
            select(ResumoCache)
            .where(ResumoCache.inquerito_id == inquerito_id)
            .where(ResumoCache.nivel == nivel)
            .where(ResumoCache.referencia_id == referencia_id)
        )
        cache = result.scalar_one_or_none()
        if cache:
            logger.debug(f"[RESUMO] Cache hit: nivel={nivel} ref={referencia_id}")
            return cache.texto_resumo
        return None

    async def _salvar_cache(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        nivel: str,
        texto: str,
        referencia_id: Optional[uuid.UUID] = None,
        modelo: Optional[str] = None,
        tokens: Optional[int] = None,
    ) -> ResumoCache:
        """Salva ou atualiza resumo no cache."""
        # Verificar se já existe para fazer upsert
        result = await db.execute(
            select(ResumoCache)
            .where(ResumoCache.inquerito_id == inquerito_id)
            .where(ResumoCache.nivel == nivel)
            .where(ResumoCache.referencia_id == referencia_id)
        )
        cache = result.scalar_one_or_none()

        if cache:
            cache.texto_resumo = texto
            cache.modelo_llm = modelo
            cache.tokens_usados = tokens
            cache.updated_at = datetime.utcnow()
        else:
            cache = ResumoCache(
                inquerito_id=inquerito_id,
                nivel=nivel,
                referencia_id=referencia_id,
                texto_resumo=texto,
                modelo_llm=modelo,
                tokens_usados=tokens,
            )
            db.add(cache)

        await db.commit()
        return cache

    # ── Métodos de geração ────────────────────────────────────────────────────

    async def resumir_documento(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        documento_id: uuid.UUID,
        texto: str,
        nome_arquivo: str = "documento.pdf",
        tipo_peca: str = "outro",
        forcar: bool = False,
    ) -> str:
        """
        Gera (ou recupera do cache) o resumo de um documento.
        Se `forcar=True`, ignora cache e regenera.
        """
        if not forcar:
            cached = await self._buscar_cache(db, inquerito_id, "documento", documento_id)
            if cached:
                return cached

        texto_curto = texto[:MAX_CHARS_DOCUMENTO]
        prompt = PROMPT_RESUMO_DOCUMENTO.format(
            nome_arquivo=nome_arquivo,
            tipo_peca=tipo_peca,
            texto=texto_curto,
        )

        try:
            result = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="economico",
                temperature=0.2,
                max_tokens=700,
            )
            resumo = result["content"].strip()
            tokens = result.get("usage", {}).get("total_tokens")
            modelo = result.get("model")
        except Exception as e:
            logger.error(f"[RESUMO] Falha ao resumir documento {documento_id}: {e}")
            resumo = f"Resumo não disponível: {str(e)[:100]}"
            tokens = None
            modelo = None

        await self._salvar_cache(
            db, inquerito_id, "documento", resumo, documento_id, modelo, tokens
        )
        logger.info(f"[RESUMO] Documento {documento_id} resumido ({len(resumo)} chars)")
        return resumo

    async def resumir_volume(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        volume_id: uuid.UUID,
        numero_volume: int,
        resumos_documentos: list[str],
        forcar: bool = False,
    ) -> str:
        """
        Consolida resumos de documentos em resumo do volume.
        """
        if not forcar:
            cached = await self._buscar_cache(db, inquerito_id, "volume", volume_id)
            if cached:
                return cached

        texto_consolidado = "\n\n---\n\n".join(resumos_documentos)[:MAX_CHARS_VOLUME]

        prompt = PROMPT_RESUMO_VOLUME.format(
            numero_volume=numero_volume,
            resumos_documentos=texto_consolidado,
        )

        try:
            result = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="economico",
                temperature=0.2,
                max_tokens=800,
            )
            resumo = result["content"].strip()
            tokens = result.get("usage", {}).get("total_tokens")
            modelo = result.get("model")
        except Exception as e:
            logger.error(f"[RESUMO] Falha ao resumir volume {volume_id}: {e}")
            resumo = f"Resumo do volume não disponível: {str(e)[:100]}"
            tokens = None
            modelo = None

        await self._salvar_cache(
            db, inquerito_id, "volume", resumo, volume_id, modelo, tokens
        )
        logger.info(f"[RESUMO] Volume {volume_id} resumido ({len(resumo)} chars)")
        return resumo

    async def resumir_caso(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        numero_inquerito: str,
        resumos_volumes: list[str],
        forcar: bool = False,
    ) -> str:
        """
        Gera o Resumo Executivo do inquérito a partir dos resumos de volumes.
        """
        if not forcar:
            cached = await self._buscar_cache(db, inquerito_id, "caso", None)
            if cached:
                return cached

        texto_consolidado = "\n\n---\n\n".join(resumos_volumes)[:MAX_CHARS_CASO]

        prompt = PROMPT_RESUMO_CASO.format(
            numero_inquerito=numero_inquerito,
            resumos_volumes=texto_consolidado,
        )

        try:
            result = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="standard",
                temperature=0.3,
                max_tokens=1000,
            )
            resumo = result["content"].strip()
            tokens = result.get("usage", {}).get("total_tokens")
            modelo = result.get("model")
        except Exception as e:
            logger.error(f"[RESUMO] Falha ao resumir caso {inquerito_id}: {e}")
            resumo = f"Resumo executivo não disponível: {str(e)[:100]}"
            tokens = None
            modelo = None

        await self._salvar_cache(
            db, inquerito_id, "caso", resumo, None, modelo, tokens
        )
        logger.info(f"[RESUMO] Caso {inquerito_id} resumido ({len(resumo)} chars)")
        return resumo

    async def obter_resumo_caso(self, db: AsyncSession, inquerito_id: uuid.UUID) -> Optional[str]:
        """Retorna o resumo executivo do caso apenas do cache (sem gerar novo)."""
        return await self._buscar_cache(db, inquerito_id, "caso", None)

    async def obter_resumo_documento(
        self, db: AsyncSession, inquerito_id: uuid.UUID, documento_id: uuid.UUID
    ) -> Optional[str]:
        """Retorna o resumo de um documento específico do cache."""
        return await self._buscar_cache(db, inquerito_id, "documento", documento_id)
