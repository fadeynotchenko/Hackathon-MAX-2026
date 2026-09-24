"""Карточки контрагентов. Все выборки ограничены владельцем карточки."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Counterparty


class CounterpartyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int, counterparty_id: int) -> Counterparty | None:
        stmt = select(Counterparty).where(
            Counterparty.id == counterparty_id, Counterparty.user_id == user_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> list[Counterparty]:
        stmt = (
            select(Counterparty).where(Counterparty.user_id == user_id).order_by(Counterparty.name)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def find_by_inn(self, user_id: int, inn: str) -> Counterparty | None:
        stmt = select(Counterparty).where(Counterparty.user_id == user_id, Counterparty.inn == inn)
        return (await self._session.execute(stmt)).scalars().first()

    async def create(
        self, user_id: int, *, name: str, inn: str | None, values: dict[str, str]
    ) -> Counterparty:
        counterparty = Counterparty(user_id=user_id, name=name, inn=inn, values=values)
        self._session.add(counterparty)
        await self._session.flush()
        return counterparty

    async def update(
        self, counterparty: Counterparty, *, name: str, inn: str | None, values: dict[str, str]
    ) -> Counterparty:
        counterparty.name = name
        counterparty.inn = inn
        counterparty.values = values
        await self._session.flush()
        # updated_at обновляет база (onupdate): без refresh чтение атрибута после
        # flush — ленивая загрузка вне greenlet и 500 на любой правке карточки.
        await self._session.refresh(counterparty)
        return counterparty

    async def delete(self, counterparty: Counterparty) -> None:
        await self._session.delete(counterparty)
        await self._session.flush()
