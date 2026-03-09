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
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,https://*.vercel.app"

    # ── Banco de Dados (Supabase) ──────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:senha@localhost:5432/postgres"
    DATABASE_URL_SYNC: str = "postgresql://postgres:senha@localhost:5432/postgres"

    # ── Supabase ───────────────────────────────────────────
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: str = "inqueritos"

    # ── Redis (Docker) ─────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Qdrant (Docker) ────────────────────────────────────
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "escrivao_chunks"

    # ── MinIO / S3 (Docker) ────────────────────────────────
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "escrivao"
    S3_SECRET_KEY: str = "escrivao_minio_2024"
    S3_BUCKET_NAME: str = "escrivao-documentos"

    # ── LLM Camada Econômica ───────────────────────────────
    LLM_ECONOMICO_PROVIDER: str = "openai"
    LLM_ECONOMICO_MODEL: str = "gpt-4.1-nano"
    LLM_ECONOMICO_BASE_URL: str = "https://api.openai.com/v1"
    LLM_ECONOMICO_API_KEY: Optional[str] = None

    # ── LLM Camada Standard ────────────────────────────────
    LLM_STANDARD_PROVIDER: str = "google"
    LLM_STANDARD_MODEL: str = "gemini-1.5-flash"
    LLM_STANDARD_BASE_URL: str = "https://generativelanguage.googleapis.com"
    LLM_STANDARD_API_KEY: Optional[str] = None

    # ── LLM Camada Premium ─────────────────────────────────
    LLM_PREMIUM_PROVIDER: str = "google"
    LLM_PREMIUM_MODEL: str = "gemini-pro-latest"
    LLM_PREMIUM_BASE_URL: str = "https://generativelanguage.googleapis.com"
    LLM_PREMIUM_API_KEY: Optional[str] = None

    # ── Gemini (Google) ────────────────────────────────────
    GEMINI_API_KEY: Optional[str] = None

    # ── DeepSeek ───────────────────────────────────────────
    DEEPSEEK_API_KEY: Optional[str] = None

    # ── OpenRouter ─────────────────────────────────────────
    OPENROUTER_API_KEY: Optional[str] = None

    model_config = {
        "env_file": (".env", "../.env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
