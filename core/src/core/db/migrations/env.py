"""Alembic env: async-движок из DatabaseConfig, метаданные из core.db.models.

Миграции применяются при старте api (core.db.migrate) и вручную через
``alembic upgrade head``. Несколько процессов сериализуются advisory-lock'ом
PostgreSQL на время транзакции миграций: второй воркер дождётся первого и
увидит, что применять нечего.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_engine_from_config

from core.db.config import DatabaseConfig
from core.db.models import Base

config = context.config
# fileConfig пересобирает root-логгер (снимает хендлеры, ставит WARNING). Из процесса
# api логи уже настроены, поэтому core.db.migrate выключает этот шаг атрибутом;
# CLI `alembic upgrade` конфигурирует логи из ini как обычно.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Произвольная стабильная константа: одна на все процессы, применяющие миграции.
MIGRATIONS_LOCK_KEY = 0x4D41584150  # "MAXAP"

target_metadata = Base.metadata


def _database_url() -> str:
    # Позволяет прогнать миграции на тестовой БД: alembic -x url=... upgrade head
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    db_config = DatabaseConfig.from_env()
    db_config.validate()
    return db_config.url()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        if connection.dialect.name == "postgresql":
            connection.execute(text(f"SELECT pg_advisory_xact_lock({MIGRATIONS_LOCK_KEY})"))
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        {"sqlalchemy.url": _database_url()}, prefix="sqlalchemy.", poolclass=None
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
