"""
Escrivão AI — Configuração do Celery
Broker e backend via Redis para processamento assíncrono.
"""

from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "escrivao",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.ingestion",
        "app.workers.orchestrator",
        "app.workers.summary_task",
        "app.workers.intimacao_task",
        "app.workers.telegram_alertas",
        "app.workers.casos_gold_task",
        "app.workers.peca_extraction_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Retry config
    task_default_retry_delay=30,
    task_max_retries=3,
    # Evita warning de deprecação no Celery 6
    broker_connection_retry_on_startup=True,
    # Beat schedule — alertas proativos Telegram
    beat_schedule={
        "alertas-intimacoes-diario": {
            "task": "app.workers.telegram_alertas.verificar_alertas_intimacoes",
            "schedule": 60 * 60 * 24,  # 24h — ajustar para crontab se precisar horário fixo
        },
    },
)
