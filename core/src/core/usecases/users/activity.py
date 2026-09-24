"""Дни активности: вход в мини-апп или реплика боту отмечают день пользователя."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import ActivityRepository
from core.domain.calendar import local_day


async def mark_active(session: AsyncSession, user_id: int, *, now: datetime | None = None) -> None:
    await ActivityRepository(session).touch(user_id, local_day(now or datetime.now(UTC)))
