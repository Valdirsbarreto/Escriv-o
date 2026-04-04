FROM python:3.12-slim

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

# Tornar o script de inicialização executável
RUN chmod +x start.sh

# Usa o script start.sh como entrypoint para executar celery e uvicorn
CMD ["./start.sh"]
