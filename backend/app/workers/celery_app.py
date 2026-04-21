"""
Escrivão AI — Configuração do Celery
Broker e backend via Redis para processamento assíncrático.

Harness operacional:
- task_failure signal  → alerta Telegram quando task falha definitivamente
- task_retry signal    → log de retry para diagnóstico
- ConsumoApi           → telemetria de latência e status de cada chamada LLM
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
        "app.workers.reconcile_task",
        "app.workers.vigilancia_task",
        "app.workers.resumo_diario_task",
    ],
)

# ── Sinais de Harness ─────────────────────────────────────────────────────────

from celery.signals import task_failure, task_retry
import logging

_logger = logging.getLogger(__name__)

# Nomes amigáveis para as tasks críticas
_TASK_LABELS = {
    "app.workers.relatorio_inicial_task.gerar_relatorio_inicial_task": "Relatório Inicial",
    "app.workers.summary_task.generate_analise_task": "Síntese Investigativa",
    "app.workers.ingestion.ingest_document": "Ingestão de Documento",
    "app.workers.relatorio_complementar_task.gerar_relatorio_complementar_task": "Relatório Complementar",
    "app.workers.orchestrator.orchestrate_new_inquerito": "Orquestrador Ingestão",
    "app.workers.reconcile_task.reconcile_pipeline_task": "Reconciliação de Pipeline",
}


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **kw):
    """
    Dispara quando uma task Celery falha definitivamente (sem mais retries).
    Usa alerta_service para mensagem humanizada + persistência no painel in-app + Telegram.
    """
    task_name = getattr(sender, "name", str(sender))
    label = _TASK_LABELS.get(task_name, task_name.split(".")[-1])
    erro_resumo = str(exception)[:300]

    inq_info = str(args[0])[:36] if args else ""

    _logger.error(f"[HARNESS] Task falhou definitivamente: {task_name} — {erro_resumo}")

    try:
        from app.services.alerta_service import enviar_alerta_sync, msg_task_failure
        titulo, mensagem, mensagem_html = msg_task_failure(label, erro_resumo, task_id or "", inq_info)
        enviar_alerta_sync("task_failure", "critico", titulo, mensagem, mensagem_html, identificador=task_id or "")
    except Exception as e:
        _logger.warning(f"[HARNESS] Falha ao enviar alerta task_failure: {e}")


@task_retry.connect
def on_task_retry(sender=None, reason=None, **kw):
    """Log de retentativas para diagnóstico — não envia alerta, só loga."""
    task_name = getattr(sender, "name", str(sender))
    _logger.warning(f"[HARNESS] Retry agendado: {task_name} — motivo: {reason}")


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
        "reconciliar-pipeline": {
            "task": "app.workers.reconcile_task.reconcile_pipeline_task",
            "schedule": 60 * 15,  # a cada 15 minutos
        },
        "beat-heartbeat-stamp": {
            "task": "app.workers.vigilancia_task.beat_heartbeat_stamp_task",
            "schedule": 60 * 5,  # a cada 5 minutos
        },
        "vigilancia-periodica": {
            "task": "app.workers.vigilancia_task.vigilancia_periodica_task",
            "schedule": 60 * 45,  # a cada 45 minutos
        },
        "resumo-diario-7h": {
            "task": "app.workers.resumo_diario_task.resumo_diario_task",
            "schedule": crontab(hour=10, minute=0),  # 10h UTC = 7h BRT
        },
    },
)
