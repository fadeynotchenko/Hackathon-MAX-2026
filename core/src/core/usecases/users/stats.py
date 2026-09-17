"""Сводка для администратора: одинаково нужна роутеру и любому другому вызывающему."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import UserRepository

ACTIVE_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class AdminStats:
    users_total: int
    users_active_24h: int


async def admin_stats(session: AsyncSession, *, now: datetime) -> AdminStats:
    users = UserRepository(session)
    return AdminStats(
        users_total=await users.count(),
        users_active_24h=await users.count_logged_in_since(now - ACTIVE_WINDOW),
    )
