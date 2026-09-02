"""Alembic environment: Config URL precedence over Settings DATABASE_URL."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from gov_service_agent.settings import get_settings

config = context.config

# CLI default: configure_logger=True (fileConfig runs).
# Programmatic callers (e.g. pytest) may set attributes["configure_logger"]=False
# to avoid disabling existing application loggers in the current process.
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name)

# F05 has no ORM models; baseline uses op.execute only.
target_metadata = None


def get_url() -> str:
    """
    Resolve migration database URL.

    Precedence:
    1. Non-empty sqlalchemy.url already on Alembic Config (integration override)
    2. Settings.database_url (normal developer CLI)
    3. fail-fast
    """
    configured = config.get_main_option("sqlalchemy.url")
    if configured is not None and configured.strip() != "":
        return configured.strip()

    settings = get_settings()
    if settings.database_url:
        return settings.database_url

    raise RuntimeError("DATABASE_URL is not configured")


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
