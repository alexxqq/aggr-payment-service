"""Alembic environment. Uses sync engine (psycopg2) for migrations."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.db import Base
from app.models import (  # noqa: F401
    AnalyticsSnapshot,
    PaymentEvent,
    PaymentIntent,
    Paywall,
    Product,
    ProductPrice,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Database URL for Alembic (sync driver)."""
    from app.core.config import get_settings

    url = get_settings().database_url
    if "+asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with sync engine (psycopg2)."""
    connectable = create_engine(
        get_url(),
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
