"""
Escrivão AI — Configuração do Celery
Broker e backend via Redis para processamento assíncrono.
"""

from celery import Celery
from celery.schedules import crontab
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
        "app.workers.relatorio_inicial_task",
        "app.workers.relatorio_complementar_task",
        "app.workers.billing_task",
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
    # Timeout — impede worker preso indefinidamente em chamadas LLM lentas
    task_time_limit=600,       # hard kill após 10 min
    task_soft_time_limit=540,  # SoftTimeLimitExceeded após 9 min (permite cleanup)
    # Retry config
    task_default_retry_delay=30,
    task_max_retries=3,
    # Evita warning de deprecação no Celery 6
    broker_connection_retry_on_startup=True,
    # Beat schedule — alertas proativos Telegram
    beat_schedule={
        "alertas-intimacoes-diario": {
            "task": "app.workers.telegram_alertas.verificar_alertas_intimacoes",
            "schedule": 60 * 60 * 24,  # 24h
        },
        "coletar-custos-externos-diario": {
            "task": "app.workers.billing_task.coletar_custos_externos_task",
            "schedule": crontab(hour=0, minute=30),  # 00:30 UTC diariamente
        },
    },
)
