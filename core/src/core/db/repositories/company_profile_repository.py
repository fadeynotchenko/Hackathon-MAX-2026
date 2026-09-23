"""Реквизиты пользователя-продавца: одна карточка на пользователя."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import CompanyProfile


class CompanyProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> CompanyProfile | None:
        stmt = select(CompanyProfile).where(CompanyProfile.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert(self, user_id: int, *, name: str, values: dict[str, str]) -> CompanyProfile:
        profile = await self.get(user_id)
        if profile is None:
            profile = CompanyProfile(user_id=user_id)
            self._session.add(profile)
        profile.name = name
        profile.values = values
        await self._session.flush()
        return profile
