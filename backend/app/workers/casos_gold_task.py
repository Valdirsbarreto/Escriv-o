"""
Escrivão AI — Worker: Ingestão de Caso Gold
Processa PDF de caso histórico e indexa na coleção casos_historicos do Qdrant.
"""

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def processar_caso_gold(
    self,
    caso_id: str,
    s3_key: str,
    titulo: str,
    tipo: str,
    metadata: dict,
):
    """
    Task Celery: baixa PDF do S3, extrai texto via pdfplumber e indexa no Banco de Casos Gold.

    Args:
        caso_id:  UUID do caso (gerado pelo endpoint antes de despachar a task)
        s3_key:   caminho do arquivo no S3 (ex: "casos_gold/uuid.pdf")
        titulo:   título do caso
        tipo:     tipo do caso (sentenca_condenatoria, laudo_pericial_referencia, etc.)
        metadata: dict com campos extras (fonte, ano, etc.)
    """
    logger.info(
        f"[CASOS-GOLD-TASK] Iniciando processamento — caso_id={caso_id} s3_key={s3_key}"
    )

    async def _run():
        # Imports pesados lazy (não bloqueiam health check do Railway)
        from app.services.storage import StorageService
        import pdfplumber
        import io
        from app.services.casos_gold_service import CasosGoldService

        # ── 1. Download do arquivo do S3 ─────────────────────────────────────
        try:
            storage = StorageService()
            conteudo_bytes = await storage.download_file(s3_key)
            logger.info(
                f"[CASOS-GOLD-TASK] Arquivo baixado: {len(conteudo_bytes)} bytes"
            )
        except Exception as e:
            logger.error(f"[CASOS-GOLD-TASK] Erro ao baixar arquivo do S3: {e}")
            raise

        # ── 2. Extração de texto via pdfplumber ───────────────────────────────
        try:
            texto_paginas = []
            with pdfplumber.open(io.BytesIO(conteudo_bytes)) as pdf:
                for page in pdf.pages:
                    texto_pagina = page.extract_text() or ""
                    if texto_pagina.strip():
                        texto_paginas.append(texto_pagina)

            texto_completo = "\n\n".join(texto_paginas).strip()
            logger.info(
                f"[CASOS-GOLD-TASK] Texto extraído: {len(texto_completo)} chars, "
                f"{len(texto_paginas)} página(s) com conteúdo"
            )
        except Exception as e:
            logger.error(f"[CASOS-GOLD-TASK] Erro ao extrair texto do PDF: {e}")
            raise

        if not texto_completo:
            logger.warning(
                f"[CASOS-GOLD-TASK] PDF sem texto extraível — caso_id={caso_id}"
            )
            return {"status": "sem_texto", "caso_id": caso_id}

        # ── 3. Indexação no Banco de Casos Gold ───────────────────────────────
        try:
            service = CasosGoldService()
            caso_id_retornado = await service.ingerir_caso(
                titulo=titulo,
                tipo=tipo,
                conteudo_texto=texto_completo,
                metadata=metadata,
            )
            logger.info(
                f"[CASOS-GOLD-TASK] Caso indexado com sucesso — caso_id={caso_id_retornado}"
            )
            return {"status": "concluido", "caso_id": caso_id_retornado}
        except Exception as e:
            logger.error(f"[CASOS-GOLD-TASK] Erro ao indexar caso: {e}")
            raise

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[CASOS-GOLD-TASK] Concluído — {result}")
        return result
    except Exception as e:
        logger.error(f"[CASOS-GOLD-TASK] Erro fatal: {e}")
        raise self.retry(exc=e)
