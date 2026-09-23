"""Карточки контрагентов: реквизиты клиента один раз, дальше подстановка."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Counterparty
from core.db.repositories import CounterpartyRepository
from core.domain.exceptions import NotFoundError, ValidationError
from core.usecases.documents.requisites import validate_requisites


@dataclass(frozen=True)
class CounterpartyView:
    id: int
    name: str
    inn: str | None
    values: dict[str, str]
    created_at: datetime
    updated_at: datetime


def to_view(counterparty: Counterparty) -> CounterpartyView:
    return CounterpartyView(
        id=counterparty.id,
        name=counterparty.name,
        inn=counterparty.inn,
        values=dict(counterparty.values),
        created_at=counterparty.created_at,
        updated_at=counterparty.updated_at,
    )


def _clean(name: str, values: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    clean, errors = validate_requisites({**values, "name": name})
    if errors:
        raise ValidationError("; ".join(errors), code="counterparty.invalid")
    if not clean.get("name"):
        raise ValidationError("Название контрагента обязательно", code="counterparty.invalid")
    return clean["name"], clean


async def list_counterparties(session: AsyncSession, *, user_id: int) -> list[CounterpartyView]:
    return [to_view(c) for c in await CounterpartyRepository(session).list_for_user(user_id)]


async def create_counterparty(
    session: AsyncSession, *, user_id: int, name: str, values: Mapping[str, str]
) -> CounterpartyView:
    clean_name, clean = _clean(name, values)
    repo = CounterpartyRepository(session)
    inn = clean.get("inn")
    if inn and await repo.find_by_inn(user_id, inn) is not None:
        raise ValidationError(f"Контрагент с ИНН {inn} уже есть", code="counterparty.duplicate_inn")
    return to_view(await repo.create(user_id, name=clean_name, inn=inn, values=clean))


async def update_counterparty(
    session: AsyncSession,
    *,
    user_id: int,
    counterparty_id: int,
    name: str,
    values: Mapping[str, str],
) -> CounterpartyView:
    repo = CounterpartyRepository(session)
    counterparty = await repo.get(user_id, counterparty_id)
    if counterparty is None:
        raise NotFoundError("Контрагент не найден", code="counterparty.not_found")
    clean_name, clean = _clean(name, values)
    return to_view(
        await repo.update(counterparty, name=clean_name, inn=clean.get("inn"), values=clean)
    )


async def delete_counterparty(session: AsyncSession, *, user_id: int, counterparty_id: int) -> None:
    repo = CounterpartyRepository(session)
    counterparty = await repo.get(user_id, counterparty_id)
    if counterparty is None:
        raise NotFoundError("Контрагент не найден", code="counterparty.not_found")
    await repo.delete(counterparty)
