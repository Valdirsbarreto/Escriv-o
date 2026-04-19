#!/bin/bash
# Escrivão AI — Script de inicialização Dinâmico (Railway/Docker)

export C_FORCE_ROOT=1

if [ "$SERVICE_ROLE" = "worker" ]; then
    echo "[START] Iniciando EXCLUSIVAMENTE o Celery Worker (SERVICE_ROLE=worker)..."
    PYTHONPATH=/app python -m alembic upgrade head
    exec celery -A app.workers.celery_app worker --loglevel=info --concurrency=4
elif [ "$SERVICE_ROLE" = "worker-beat" ]; then
    echo "[START] Iniciando Celery Worker + Beat Scheduler (SERVICE_ROLE=worker-beat)..."
    echo "[START] ATENÇÃO: apenas UMA instância deve rodar com worker-beat para evitar tasks duplicadas."
    PYTHONPATH=/app python -m alembic upgrade head
    exec celery -A app.workers.celery_app worker --beat --loglevel=info --concurrency=2
elif [ "$SERVICE_ROLE" = "api" ]; then
    echo "[START] Iniciando EXCLUSIVAMENTE a API Uvicorn (SERVICE_ROLE=api)..."
    PYTHONPATH=/app alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
else
    echo "[START] Iniciando MODO MONOLITO (Celery + Beat + Uvicorn)..."
    PYTHONPATH=/app alembic upgrade head
    celery -A app.workers.celery_app worker --beat --loglevel=info --concurrency=2 &
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
fi
