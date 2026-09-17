"""Refresh-токены: хранение хешей, ротация, отзыв семьи, чистка просроченных."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, user_id: int, token_hash: str, family_id: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id, token_hash=token_hash, family_id=family_id, expires_at=expires_at
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_rotated(
        self, token: RefreshToken, *, replaced_by_hash: str, now: datetime
    ) -> bool:
        """Пометить токен ротированным. False — его уже ротировал параллельный запрос.

        Условие ``revoked_at IS NULL`` в UPDATE делает ротацию атомарной: два
        одновременных /auth/refresh одним токеном на READ COMMITTED иначе оба
        прошли бы, и украденная копия осталась бы незамеченной."""
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, replaced_by_hash=replaced_by_hash)
        )
        await self._session.refresh(token)
        return int(result.rowcount or 0) == 1

    async def revoke_family(self, family_id: str, *, now: datetime) -> int:
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return int(result.rowcount or 0)

    async def revoke_all_for_user(self, user_id: int, *, now: datetime) -> int:
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return int(result.rowcount or 0)

    async def delete_expired_for_user(self, user_id: int, *, before: datetime) -> int:
        """Удалить токены пользователя, которые ни при каких условиях уже не примут.

        Зовётся при каждом входе: каждое открытие мини-аппа выдаёт новую семью,
        и без чистки таблица росла бы без предела. Отозванные, но не истёкшие
        токены остаются — по ним ловится повторное использование."""
        result = await self._session.execute(
            delete(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.expires_at < before
            )
        )
        return int(result.rowcount or 0)
