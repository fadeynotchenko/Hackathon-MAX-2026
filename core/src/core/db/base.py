"""Движок и сессии SQLAlchemy. Таблицы создают миграции, не этот модуль."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.db.config import DatabaseConfig

logger = logging.getLogger(__name__)

engine: AsyncEngine | None = None
session_maker: async_sessionmaker[AsyncSession] | None = None


async def init_db(config: DatabaseConfig) -> None:
    global engine, session_maker
    engine = create_async_engine(
        config.url(),
        pool_pre_ping=True,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_timeout=config.pool_timeout,
        pool_recycle=config.pool_recycle,
        # statement_timeout на стороне сервера: зависший запрос не держит
        # соединение из пула дольше N мс.
        connect_args={"server_settings": {"statement_timeout": str(config.statement_timeout_ms)}},
    )
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await ping_db()
    logger.info("database ready", extra={"event": "db.ready", "fields": {"host": config.host}})


def use_session_maker(
    maker: async_sessionmaker[AsyncSession], eng: AsyncEngine | None = None
) -> None:
    """Подменить фабрику сессий (тесты на SQLite)."""
    global engine, session_maker
    session_maker = maker
    engine = eng


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession]:
    """Одна сессия = одна единица работы: commit на выходе, rollback при исключении."""
    if session_maker is None:
        raise RuntimeError("init_db() не вызван")
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def ping_db() -> None:
    if session_maker is None:
        raise RuntimeError("init_db() не вызван")
    async with session_maker() as session:
        await session.execute(text("SELECT 1"))


async def close_db() -> None:
    global engine, session_maker
    if engine is not None:
        await engine.dispose()
    engine = None
    session_maker = None
