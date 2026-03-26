FROM python:3.11-slim

# Dependências de sistema (Tesseract + Poppler para OCR/PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-por \
    poppler-utils \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements PRIMEIRO — só reinstala quando requirements.txt mudar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Railway injeta PORT via env var
EXPOSE 8000

CMD ["sh", "-c", "PYTHONPATH=/app alembic upgrade head || true && celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 & uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
