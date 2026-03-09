"""
Escrivão AI — Configuração do Banco de Dados
Engine assíncrono SQLAlchemy + sessão + dependency FastAPI.
Compatível com Supabase (connection pooler via PgBouncer).
"""

import ssl

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Supabase usa SSL — detectar se é conexão remota
_is_remote = "supabase" in settings.DATABASE_URL or "localhost" not in settings.DATABASE_URL

_engine_kwargs = {
    "echo": settings.APP_ENV == "development",
    "pool_size": 10,
    "max_overflow": 5,
    "pool_pre_ping": True,  # Importante para conexões remotas
}

# SSL para Supabase
if _is_remote:
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    _engine_kwargs["connect_args"] = {"ssl": ssl_context}

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

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
