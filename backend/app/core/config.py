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
    QDRANT_COLLECTION_CASOS: str = "casos_historicos"

    # ── MinIO / S3 (Docker) ────────────────────────────────
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "escrivao"
    S3_SECRET_KEY: str = "escrivao_minio_2024"
    S3_BUCKET_NAME: str = "escrivao-documentos"

    # ── LLM Camada Econômica ───────────────────────────────
    LLM_ECONOMICO_PROVIDER: str = "google"
    LLM_ECONOMICO_MODEL: str = "gemini-1.5-flash-8b"
    LLM_ECONOMICO_BASE_URL: str = "https://generativelanguage.googleapis.com"
    LLM_ECONOMICO_API_KEY: Optional[str] = None  # Deprecated — todos os tiers usam GEMINI_API_KEY
    LLM_ECONOMICO_TEMPERATURE: float = 0.1  # Foco em consistência para NER/classificação

    # ── LLM Camada Standard / Vision ──────────────────────
    LLM_STANDARD_PROVIDER: str = "google"
    LLM_STANDARD_MODEL: str = "gemini-1.5-flash"
    LLM_STANDARD_BASE_URL: str = "https://generativelanguage.googleapis.com"
    LLM_STANDARD_API_KEY: Optional[str] = None  # Deprecated — todos os tiers usam GEMINI_API_KEY

    # ── LLM Camada Premium ─────────────────────────────────
    LLM_PREMIUM_PROVIDER: str = "google"
    LLM_PREMIUM_MODEL: str = "gemini-1.5-pro"
    LLM_PREMIUM_BASE_URL: str = "https://generativelanguage.googleapis.com"
    LLM_PREMIUM_API_KEY: Optional[str] = None  # Deprecated — todos os tiers usam GEMINI_API_KEY

    # ── OpenAI (Deprecated — mantido para rollback de emergência) ──
    OPENAI_API_KEY: Optional[str] = None

    # ── Gemini (Google) ────────────────────────────────────
    GEMINI_API_KEY: Optional[str] = None

    # ── DeepSeek (Fallback prioritário) ────────────────────
    DEEPSEEK_API_KEY: Optional[str] = None

    # ── OpenRouter ─────────────────────────────────────────
    OPENROUTER_API_KEY: Optional[str] = None

    # ── direct.data (BigDataCorp) — OSINT Sprint 6 ─────────
    DIRECTDATA_API_TOKEN: str = ""
    DIRECTDATA_BASE_URL: str = "https://apiv3.directd.com.br"

    # ── Web Search (Serper.dev) ────────────────────────────
    SERPER_API_KEY: str = "445238390f1dc65cc43ec5662d87f0aae7b69d36"

    # ── Cripto / Blockchain OSINT ──────────────────────────
    CHAINABUSE_API_KEY: Optional[str] = None
    ETHERSCAN_API_KEY: Optional[str] = None
    TRONSCAN_API_KEY: Optional[str] = None

    # ── Google Calendar ─────────────────────────────────────
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_CALENDAR_REFRESH_TOKEN: Optional[str] = None
    GOOGLE_CALENDAR_ID: str = "primary"  # ID do calendário (primary = calendário principal)

    # ── Controle de Orçamento LLM ─────────────────────────────
    BUDGET_BRL: float = 250.0          # Limite mensal em Reais (Google AI Studio Nível 1)
    BUDGET_ALERT_BRL: float = 200.0    # Dispara alerta Telegram ao atingir este valor
    COTACAO_DOLAR: float = 5.80        # Cotação USD→BRL para estimativa (atualizar manualmente)

    # ── Telegram Bot ─────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    # IDs Telegram autorizados (separados por vírgula). Vazio = bloqueia todos.
    TELEGRAM_ALLOWED_USER_IDS: str = ""
    # Token de verificação do webhook (gerado livremente, min 32 chars recomendado)
    TELEGRAM_WEBHOOK_SECRET: str = ""

    model_config = {
        "env_file": (".env", "../.env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

# ── Auto-Sincronização de Redis (Railway) ──────────────────────────
# Priorizamos a URL completa se estiver no ambiente (REDIS_URL ou REDIS_PRIVATE_URL).
# Se a URL não contiver autenticação mas REDISPASSWORD estiver definido, injetamos.
# Caso contrário, construímos a partir das variáveis individuais da Railway.
import os

_env_redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL")
_redis_pwd = os.getenv("REDISPASSWORD")

if _env_redis_url:
    # Se a URL não tem auth (sem '@') mas temos senha, injetar
    if _redis_pwd and "@" not in _env_redis_url:
        _env_redis_url = _env_redis_url.replace("redis://", f"redis://:{_redis_pwd}@", 1)
    settings.REDIS_URL = _env_redis_url
else:
    _redis_host = os.getenv("REDISHOST")
    _redis_port = os.getenv("REDISPORT", "6379")

    if _redis_host and _redis_pwd:
        # Formato: redis://:senha@host:porta/0
        settings.REDIS_URL = f"redis://:{_redis_pwd}@{_redis_host}:{_redis_port}/0"
    elif _redis_host:
        # Sem senha (não recomendado para Railway)
        settings.REDIS_URL = f"redis://{_redis_host}:{_redis_port}/0"


# ── Auto-Sincronização de Banco de Dados (PostgreSQL Sync vs Async) ──────────
# Se estivermos em produção e o DATABASE_URL_SYNC ainda for o default (localhost),
# vamos derivá-lo automaticamente do DATABASE_URL principal, removendo o driver '+asyncpg'.
if "localhost" not in settings.DATABASE_URL and "localhost" in settings.DATABASE_URL_SYNC:
    # Transforma postgresql+asyncpg://... em postgresql://...
    settings.DATABASE_URL_SYNC = settings.DATABASE_URL.replace("+asyncpg", "")

