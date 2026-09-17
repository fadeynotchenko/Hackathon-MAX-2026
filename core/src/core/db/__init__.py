"""Хранилища: PostgreSQL (SQLAlchemy async) и Redis.

Весь доступ к базе из прикладного кода — только через ``core.db.repositories``.
Схемой владеют миграции Alembic (``core/db/migrations``), а не ``create_all``.
"""

from .base import close_db, get_session, init_db, ping_db
from .redis import close_redis, get_redis, init_redis, new_client, ping_redis

__all__ = [
    "close_db",
    "close_redis",
    "get_redis",
    "get_session",
    "init_db",
    "init_redis",
    "ping_db",
    "ping_redis",
]
