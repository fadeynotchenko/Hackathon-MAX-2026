"""Пользователи. Репозиторий — тонкая обёртка над сессией без бизнес-правил."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import User

# «Поле не пришло от источника» — не то же, что «источник прислал пусто»:
# у бота нет аватара пользователя, и событие бота не должно стирать тот,
# что сохранил вход через мини-апп.
KEEP: Any = object()


@dataclass(frozen=True)
class UserUpsert:
    max_user_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    photo_url: str | None = KEEP
    via: str = "mini_app"


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_max_id(self, max_user_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.max_user_id == max_user_id))
        return result.scalar_one_or_none()

    async def upsert_from_max(self, data: UserUpsert, *, touch_login: bool, now: datetime) -> User:
        """Создать пользователя или обновить профиль данными платформы.

        Профиль берётся из свежих данных MAX: они авторитетнее того, что лежит
        у нас, — но только те поля, которые источник действительно прислал.
        """
        user = await self.get_by_max_id(data.max_user_id)
        if user is None:
            user = await self._insert_or_get_existing(data)
        if data.first_name or not user.first_name:
            user.first_name = data.first_name
        user.last_name = data.last_name
        user.username = data.username
        if data.language_code is not None:
            user.language_code = data.language_code
        if data.photo_url is not KEEP:
            user.photo_url = data.photo_url
        if touch_login:
            user.last_login_at = now
        await self._session.flush()
        return user

    async def _insert_or_get_existing(self, data: UserUpsert) -> User:
        """Вставка под savepoint: два параллельных входа одного нового пользователя
        (React StrictMode дважды запускает эффект, два устройства входят разом)
        оба видят «пользователя нет». Первый вставляет, второй ловит нарушение
        уникальности, откатывает только savepoint и читает уже созданную строку."""
        try:
            async with self._session.begin_nested():
                user = User(max_user_id=data.max_user_id, first_seen_via=data.via)
                self._session.add(user)
                await self._session.flush()
            return user
        except IntegrityError:
            existing = await self.get_by_max_id(data.max_user_id)
            if existing is None:
                raise
            return existing

    async def delete(self, user_id: int) -> bool:
        """Удалить пользователя со всем, что ему принадлежит: каскад делает сама БД
        (ON DELETE CASCADE), ORM-каскад обнулял бы внешние ключи дочерних строк."""
        result = await self._session.execute(delete(User).where(User.id == user_id))
        return int(result.rowcount or 0) == 1

    async def count(self) -> int:
        return int(await self._session.scalar(select(func.count()).select_from(User)) or 0)

    async def count_logged_in_since(self, since: datetime) -> int:
        stmt = select(func.count()).select_from(User).where(User.last_login_at >= since)
        return int(await self._session.scalar(stmt) or 0)

    async def count_created_before(self, moment: datetime) -> int:
        stmt = select(func.count()).select_from(User).where(User.created_at < moment)
        return int(await self._session.scalar(stmt) or 0)

    async def created_between(self, since: datetime, until: datetime) -> list[datetime]:
        stmt = select(User.created_at).where(User.created_at >= since, User.created_at < until)
        return list((await self._session.execute(stmt)).scalars())
