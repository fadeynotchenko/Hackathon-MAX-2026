"""Свои организации пользователя. Все выборки ограничены владельцем."""

from __future__ import annotations

import hashlib

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Organization


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int, organization_id: int) -> Organization | None:
        stmt = select(Organization).where(
            Organization.id == organization_id, Organization.user_id == user_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> list[Organization]:
        stmt = (
            select(Organization)
            .where(Organization.user_id == user_id)
            .order_by(Organization.is_default.desc(), Organization.name, Organization.id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def get_default(self, user_id: int) -> Organization | None:
        stmt = select(Organization).where(
            Organization.user_id == user_id, Organization.is_default.is_(True)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def find_by_inn(self, user_id: int, inn: str) -> Organization | None:
        stmt = select(Organization).where(Organization.user_id == user_id, Organization.inn == inn)
        return (await self._session.execute(stmt)).scalars().first()

    async def create(
        self, user_id: int, *, name: str, inn: str | None, values: dict[str, str]
    ) -> Organization:
        organization = Organization(
            user_id=user_id, name=name, inn=inn, values=values, is_default=False
        )
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def update(
        self, organization: Organization, *, name: str, inn: str | None, values: dict[str, str]
    ) -> Organization:
        organization.name = name
        organization.inn = inn
        organization.values = values
        await self._session.flush()
        await self._session.refresh(organization)
        return organization

    async def make_default(self, organization: Organization) -> Organization:
        await self._session.execute(
            update(Organization)
            .where(Organization.user_id == organization.user_id, Organization.id != organization.id)
            .values(is_default=False)
        )
        organization.is_default = True
        await self._session.flush()
        # Массовый UPDATE выше сбрасывает загруженные поля: без refresh их чтение
        # в async-сессии полезло бы в базу синхронно (MissingGreenlet).
        await self._session.refresh(organization)
        return organization

    async def delete(self, organization: Organization) -> None:
        await self._session.delete(organization)
        await self._session.flush()

    async def set_mark(self, organization: Organization, kind: str, data: bytes | None) -> None:
        """Подпись или печать (``kind``) картинкой; ``None`` — убрать."""
        setattr(organization, kind, data)
        setattr(organization, f"{kind}_sha256", hashlib.sha256(data).hexdigest() if data else None)
        await self._session.flush()
        # updated_at ставит база: без refresh чтение после flush пошло бы в неё синхронно.
        await self._session.refresh(organization, ["updated_at"])

    async def mark(self, organization_id: int, kind: str) -> bytes | None:
        column = getattr(Organization, kind)
        stmt = select(column).where(Organization.id == organization_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()
