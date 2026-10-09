"""Alembic environment: how migration scripts connect to the database.

`alembic upgrade head` imports this file. Where the URL comes from, in order:
1. `sqlalchemy.url` set programmatically (tests do this),
2. otherwise HAGGLE_DATABASE_URL via haggle_core.settings (local .env or Secret Manager in prod).

Migrations use a plain sync engine: they are a one-off script, async brings nothing here.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from haggle_core.db import Base
from haggle_core.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Autogenerate compares the live database against this metadata to propose changes.
target_metadata = Base.metadata


def _database_url() -> str:
    return (
        config.get_main_option("sqlalchemy.url") or get_settings().database_url.get_secret_value()
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of executing it (useful for review)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
