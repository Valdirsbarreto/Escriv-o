"""
Escrivão AI — Configuração do Banco de Dados
Engine assíncrono SQLAlchemy + sessão + dependency FastAPI.
Compatível com Supabase Transaction Pooler (PgBouncer, porta 6543).
"""

import ssl
from urllib.parse import quote, urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _encode_password_in_url(url: str) -> str:
    """URL-encoda a senha na connection string (ex: ã → %C3%A3)."""
    parsed = urlparse(url)
    if parsed.password:
        encoded_password = quote(parsed.password, safe="")
        if parsed.port:
            netloc = f"{parsed.username}:{encoded_password}@{parsed.hostname}:{parsed.port}"
        else:
            netloc = f"{parsed.username}:{encoded_password}@{parsed.hostname}"
        return urlunparse(parsed._replace(netloc=netloc))
    return url


_db_url = _encode_password_in_url(settings.DATABASE_URL)

# SQLAlchemy asyncio exige driver asyncpg — corrige esquema se necessário
if _db_url.startswith("postgresql://") or _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)

_parsed = urlparse(_db_url)

_is_remote = "supabase" in _db_url or "localhost" not in _db_url
# Porta 6543 = Supabase Transaction Pooler (PgBouncer).
# Prepared statements devem ser desabilitados nesse modo.
_is_pooler = _parsed.port == 6543

_engine_kwargs = {
    "echo": settings.APP_ENV == "development",
    "pool_size": 2,
    "max_overflow": 3,     # máx 5 conexões total (Supabase free tier ≈ 6)
    "pool_pre_ping": True,
    "pool_recycle": 300,   # recicla a cada 5min — evita conexões mortas
    "pool_timeout": 30,
}

if _is_remote:
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connect_args: dict = {
        "ssl": ssl_context,
        "timeout": 30,  # asyncpg: segundos para estabelecer a conexão
        "statement_cache_size": 0,  # desabilita prepared statements nomeados (compatível com PgBouncer em qualquer modo)
    }

    if _is_pooler:
        # PgBouncer em transaction mode: desabilita JIT também
        connect_args["server_settings"] = {"jit": "off"}

    _engine_kwargs["connect_args"] = connect_args

engine = create_async_engine(_db_url, **_engine_kwargs)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Classe base para todos os modelos SQLAlchemy."""
    pass


async def get_db():
    """Dependency FastAPI que fornece sessão assíncrona."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
