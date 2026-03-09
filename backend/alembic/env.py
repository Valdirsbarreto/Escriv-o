"""
Escrivão AI — Alembic env.py
Configuração para auto-geração de migrations a partir dos modelos SQLAlchemy.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Importar Base e todos os modelos para detecção automática
from app.core.database import Base
import app.models  # noqa: F401 — importa todos os modelos

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Gera SQL sem conexão ao banco."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Executa migrations com conexão ao banco."""
    from app.core.config import settings
    from app.core.database import _encode_password_in_url
    
    sync_url = _encode_password_in_url(settings.DATABASE_URL_SYNC)
    
    config_section = config.get_section(config.config_ini_section, {})
    config_section["sqlalchemy.url"] = sync_url

    connectable = engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    
    import ssl
    connect_args = {}
    if "supabase" in sync_url or "localhost" not in sync_url:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl_context"] = ctx # Para psycopg2 o kwarg é ssl_context

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            **({"connect_args": connect_args} if connect_args else {})
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
