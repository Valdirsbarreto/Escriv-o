"""
Escrivão AI — Configuração Central
Carrega variáveis de ambiente via Pydantic BaseSettings.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do .env"""

    # ── Aplicação ──────────────────────────────────────────
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "troque-esta-chave-em-producao"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # ── Banco de Dados ─────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://escrivao:escrivao_dev_2024@localhost:5432/escrivao_db"
    DATABASE_URL_SYNC: str = "postgresql://escrivao:escrivao_dev_2024@localhost:5432/escrivao_db"

    # ── Redis ──────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Qdrant ─────────────────────────────────────────────
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "escrivao_chunks"

    # ── MinIO / S3 ─────────────────────────────────────────
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "escrivao"
    S3_SECRET_KEY: str = "escrivao_minio_2024"
    S3_BUCKET_NAME: str = "escrivao-documentos"

    # ── LLM Camada Econômica ───────────────────────────────
    LLM_ECONOMICO_PROVIDER: str = "openai"
    LLM_ECONOMICO_MODEL: str = "gpt-4.1-nano"
    LLM_ECONOMICO_API_KEY: Optional[str] = None

    # ── LLM Camada Premium ─────────────────────────────────
    LLM_PREMIUM_PROVIDER: str = "openai"
    LLM_PREMIUM_MODEL: str = "gpt-4.1"
    LLM_PREMIUM_API_KEY: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
