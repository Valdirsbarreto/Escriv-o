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
    include=["app.workers.ingestion"],
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
)
