"""
Escrivão AI — Alertas proativos via Telegram
Celery beat task: verifica intimações próximas e envia alertas ao Delegado.
"""

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.telegram_alertas.verificar_alertas_intimacoes")
def verificar_alertas_intimacoes():
    """
    Verifica intimações nas próximas 48h e envia alertas via Telegram.
    Agendado pelo Celery beat para rodar diariamente às 07:00 (Brasília).
    """
    asyncio.run(_run())


async def _run():
    from app.core.database import AsyncSessionLocal
    from app.core.config import settings
    from app.services.telegram_copiloto import enviar_alertas_intimacoes

    # Verificar se bot está configurado
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ALLOWED_USER_IDS:
        logger.warning("[TELEGRAM-ALERTAS] Bot não configurado — skip")
        return

    # Carregar user_ids autorizados (envia para todos)
    user_ids = []
    for part in settings.TELEGRAM_ALLOWED_USER_IDS.split(","):
        part = part.strip()
        if part.isdigit():
            user_ids.append(int(part))

    if not user_ids:
        logger.warning("[TELEGRAM-ALERTAS] Nenhum user_id autorizado configurado")
        return

    async with AsyncSessionLocal() as db:
        try:
            alertas = await enviar_alertas_intimacoes(db)
        except Exception as e:
            logger.error(f"[TELEGRAM-ALERTAS] Erro ao buscar alertas: {e}", exc_info=True)
            return

    if not alertas:
        logger.info("[TELEGRAM-ALERTAS] Nenhuma intimação próxima — sem alertas")
        return

    from app.services.telegram_bot import TelegramBotService
    bot = TelegramBotService()

    cabecalho = f"⏰ <b>Alertas de Agenda — {len(alertas)} oitiva(s) próxima(s)</b>\n"

    for user_id in user_ids:
        try:
            await bot.send_message(user_id, cabecalho + "\n\n".join(alertas))
            logger.info(f"[TELEGRAM-ALERTAS] Alerta enviado para user_id={user_id} ({len(alertas)} intimações)")
        except Exception as e:
            logger.error(f"[TELEGRAM-ALERTAS] Falha ao enviar para user_id={user_id}: {e}")
