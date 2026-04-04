"""
Escrivão AI — Task Celery: Processamento de Intimações
OCR + extração LLM + criação de evento no Google Agenda + vínculo ao inquérito.
"""

import asyncio
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def processar_intimacao(self, intimacao_id: str):
    """
    Task Celery que processa uma intimação recém-uploadada.

    Fluxo:
    1. Carrega o documento (bytes) do storage
    2. OCR + extração LLM de dados estruturados
    3. Busca o inquérito correspondente pelo número extraído
    4. Cria evento no Google Agenda
    5. Atualiza a Intimacao no banco com todos os dados
    """
    logger.info(f"[INTIMACAO-TASK] Iniciando — intimacao_id={intimacao_id}")

    async def _run():
        from app.models.intimacao import Intimacao
        from app.models.inquerito import Inquerito
        from app.models.documento import Documento
        from app.services.intimacao_extractor import IntimacaoExtractor
        from app.services.google_calendar_service import GoogleCalendarService
        from app.services.storage import StorageService

        async_url = _encode_password_in_url(settings.DATABASE_URL)
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        async_url = async_url.replace("postgres://", "postgresql+asyncpg://", 1)

        import ssl
        connect_args = {"statement_cache_size": 0}
        if "supabase" in async_url or "localhost" not in async_url:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx

        engine = create_async_engine(
            async_url, connect_args=connect_args, poolclass=NullPool
        )
        AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        intim_uuid = uuid.UUID(intimacao_id)

        async with AsyncSession_() as db:
            intim = await db.get(Intimacao, intim_uuid)
            if not intim:
                logger.error(f"[INTIMACAO-TASK] Intimação não encontrada: {intimacao_id}")
                return

            # ── 1. Carregar documento do storage ─────────────────────
            doc = None
            content = b""
            content_type = "application/pdf"

            if intim.documento_id:
                doc = await db.get(Documento, intim.documento_id)

            # Determina o path: via Documento ou direto da Intimacao (upload avulso)
            file_path = (doc.storage_path if doc else None) or intim.storage_path
            file_name = (doc.nome_arquivo if doc else None) or (
                intim.storage_path.rsplit("/", 1)[-1] if intim.storage_path else ""
            )

            if file_path:
                try:
                    storage = StorageService()
                    content = await storage.download_file(file_path)
                    ext = file_name.lower().rsplit(".", 1)[-1] if file_name else ""
                    if ext in ("png", "jpg", "jpeg"):
                        content_type = f"image/{ext}"
                    elif ext == "tiff":
                        content_type = "image/tiff"
                except Exception as e:
                    logger.error(f"[INTIMACAO-TASK] Erro ao baixar documento: {e}")

            # ── 2. OCR + extração via Gemini Vision (única chamada) ───────
            extractor = IntimacaoExtractor()
            texto = ""
            dados = {}
            if content:
                try:
                    texto, dados_raw = await extractor.extrair_tudo(content, content_type)
                    logger.info(
                        f"[INTIMACAO-TASK] Gemini Vision extraiu {len(texto)} chars | "
                        f"nome={dados_raw.get('intimado_nome')!r} "
                        f"data={dados_raw.get('data_oitiva')!r} "
                        f"inq={dados_raw.get('numero_inquerito')!r}"
                    )
                    if dados_raw:
                        dados = extractor._normalizar_dados(dados_raw)
                    elif texto:
                        # Fallback: extração só de texto → LLM tenta estruturar
                        dados = await extractor.extrair_dados(texto)
                except Exception as e:
                    logger.error(f"[INTIMACAO-TASK] Erro na extração Gemini Vision: {e}")

            # Salvar texto e dados extraídos na intimação
            intim.texto_extraido = texto[:10000] if texto else None
            if dados.get("intimado_nome"):
                intim.intimado_nome = dados["intimado_nome"]
            if dados.get("intimado_cpf"):
                intim.intimado_cpf = dados["intimado_cpf"]
            if dados.get("intimado_qualificacao"):
                intim.intimado_qualificacao = dados["intimado_qualificacao"]
            if dados.get("numero_inquerito"):
                intim.numero_inquerito_extraido = dados["numero_inquerito"]
            if dados.get("data_oitiva"):
                intim.data_oitiva = dados["data_oitiva"]
            if dados.get("local_oitiva"):
                intim.local_oitiva = dados["local_oitiva"]

            # ── 3. Match com inquérito no banco ───────────────────────
            if not intim.inquerito_id and dados.get("numero_inquerito"):
                result = await db.execute(
                    select(Inquerito).where(
                        Inquerito.numero == dados["numero_inquerito"]
                    )
                )
                inquerito = result.scalar_one_or_none()
                if inquerito:
                    intim.inquerito_id = inquerito.id
                    logger.info(
                        f"[INTIMACAO-TASK] Vinculado ao inquérito {inquerito.numero}"
                    )
                else:
                    logger.warning(
                        f"[INTIMACAO-TASK] Inquérito '{dados['numero_inquerito']}' não encontrado no banco"
                    )

            # ── 4. Criar evento no Google Agenda ──────────────────────
            if intim.data_oitiva and intim.intimado_nome:
                # Se a data da oitiva já passou, aguarda confirmação do usuário
                if intim.data_oitiva < datetime.utcnow():
                    logger.warning(
                        f"[INTIMACAO-TASK] Data passada ({intim.data_oitiva}) — aguardando confirmação"
                    )
                    intim.status = "data_passada"
                else:
                    try:
                        gcal = GoogleCalendarService()
                        evento = gcal.criar_evento_oitiva(
                            intimado_nome=intim.intimado_nome,
                            data_oitiva=intim.data_oitiva,
                            numero_inquerito=intim.numero_inquerito_extraido,
                            local_oitiva=intim.local_oitiva,
                            qualificacao=intim.intimado_qualificacao,
                        )
                        intim.google_event_id = evento.get("event_id")
                        intim.google_event_url = evento.get("event_url")
                        intim.status = "agendada"
                        logger.info(
                            f"[INTIMACAO-TASK] Evento Google criado: {intim.google_event_id}"
                        )
                    except RuntimeError as e:
                        logger.warning(f"[INTIMACAO-TASK] Google Calendar não configurado: {e}")
                        intim.status = "sem_calendario"
                    except Exception as e:
                        logger.error(f"[INTIMACAO-TASK] Erro ao criar evento Google: {e}")
                        intim.status = "erro_agenda"
            else:
                missing = []
                if not intim.data_oitiva:
                    missing.append("data_oitiva")
                if not intim.intimado_nome:
                    missing.append("intimado_nome")
                logger.warning(
                    f"[INTIMACAO-TASK] Evento não criado — campos ausentes: {missing}"
                )
                intim.status = "dados_incompletos"

            logger.info(
                f"[INTIMACAO-TASK] Commit — nome={intim.intimado_nome!r} "
                f"data={intim.data_oitiva!r} status={intim.status!r}"
            )
            await db.commit()
            logger.info(f"[INTIMACAO-TASK] Concluído — intimacao_id={intimacao_id}")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[INTIMACAO-TASK] Falha fatal: {exc}", exc_info=True)
        raise self.retry(exc=exc)
