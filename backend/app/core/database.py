"""
Escrivão AI — Configuração do Banco de Dados
Engine assíncrono SQLAlchemy + sessão + dependency FastAPI.
Compatível com Supabase (connection pooler via PgBouncer).
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
        # Reconstruir netloc com senha encodada
        if parsed.port:
            netloc = f"{parsed.username}:{encoded_password}@{parsed.hostname}:{parsed.port}"
        else:
            netloc = f"{parsed.username}:{encoded_password}@{parsed.hostname}"
        return urlunparse(parsed._replace(netloc=netloc))
    return url


_db_url = _encode_password_in_url(settings.DATABASE_URL)

# Supabase usa SSL — detectar se é conexão remota
_is_remote = "supabase" in _db_url or "localhost" not in _db_url

_engine_kwargs = {
    "echo": settings.APP_ENV == "development",
    "pool_size": 2,
    "max_overflow": 3,     # máximo 5 conexões total — Supabase free tier suporta ~6
    "pool_pre_ping": True,
    "pool_recycle": 300,   # recicla conexões a cada 5min (evita conexões mortas)
    "pool_timeout": 30,    # espera até 30s por conexão do pool
}

if _is_remote:
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    _engine_kwargs["connect_args"] = {
        "ssl": ssl_context,
        "timeout": 10,  # asyncpg: timeout de conexão em segundos
    }

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
