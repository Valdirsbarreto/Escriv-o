#!/bin/bash
# Escrivão AI — Script de inicialização
# Garante que alembic, celery e uvicorn sobem corretamente

echo "[START] Rodando migrações..."
alembic upgrade head || echo "[START] Aviso: alembic retornou erro, continuando mesmo assim..."

echo "[START] Iniciando Celery worker em background..."
celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 &

echo "[START] Iniciando Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
