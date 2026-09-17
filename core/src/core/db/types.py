"""Типы колонок, одинаково ведущие себя в PostgreSQL и SQLite (тесты).

SQLite хранит datetime строкой без зоны и отдаёт naive-значения; сравнение
с aware-датой из кода падало бы TypeError. Декоратор приводит всё к UTC
с зоной в обе стороны, поэтому код выше работает только с aware-датами.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.types import TypeDecorator

# SQLite автоинкрементит только INTEGER PRIMARY KEY, а BIGINT — нет.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class UtcDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
