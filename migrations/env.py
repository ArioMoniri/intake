"""Alembic environment (INT-030). Sync engine on purpose: migrations are a
bounded administrative action, not request-path work (the app's async engine
shares the same models). The URL comes from configuration or environment —
never a literal in versioned config; the fallback is the compose dev tier."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from intake_platform.db.models import Base
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_DEV_URL = "postgresql+psycopg://intake:intake-dev-only@127.0.0.1:5432/intake"


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return os.environ.get("INTAKE_DATABASE_URL", _DEV_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
