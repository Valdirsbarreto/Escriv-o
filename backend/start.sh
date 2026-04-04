#!/bin/bash
# Escrivão AI — Script de inicialização
# Alembic NÃO roda aqui — executa no buildCommand do railway.toml (fora do healthcheck window)

export C_FORCE_ROOT=1

echo "[START] Iniciando Celery worker em background..."
celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 &

echo "[START] Iniciando Uvicorn (PID 1)..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
