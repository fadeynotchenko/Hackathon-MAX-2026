"""Дни активности пользователей: одна строка на пользователя и день."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import UserActivityDay


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def touch(self, user_id: int, day: date) -> None:
        """Отметить день. Два входа одного пользователя разом оба видят «дня нет»:
        вставка под savepoint, второй ловит нарушение ключа и ничего не портит."""
        if await self._session.get(UserActivityDay, (user_id, day)) is not None:
            return
        try:
            async with self._session.begin_nested():
                self._session.add(UserActivityDay(user_id=user_id, day=day))
                await self._session.flush()
        except IntegrityError:
            return

    async def between(self, since: date, until: date) -> list[tuple[int, date]]:
        """Пары (пользователь, день) с ``since`` включительно по ``until`` не включая."""
        stmt = select(UserActivityDay.user_id, UserActivityDay.day).where(
            UserActivityDay.day >= since, UserActivityDay.day < until
        )
        return [(int(user_id), day) for user_id, day in await self._session.execute(stmt)]
