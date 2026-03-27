FROM python:3.12-slim

# Dependências de sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-por \
    poppler-utils \
    libpq-dev \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements PRIMEIRO — pip install só roda quando requirements.txt mudar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "PYTHONPATH=/app alembic upgrade head || true && celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 & uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
