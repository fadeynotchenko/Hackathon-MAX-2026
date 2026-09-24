"""Свои организации пользователя: подставляются в документ как сторона продавца.

Организаций может быть несколько (ООО и ИП одного владельца), одна из них —
основная. Первая заведённая становится основной сама; при удалении основной
её место занимает следующая, чтобы у документа без выбора всегда был продавец.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Organization
from core.db.repositories import OrganizationRepository
from core.domain.exceptions import NotFoundError, ValidationError
from core.usecases.documents.requisites import validate_requisites


@dataclass(frozen=True)
class OrganizationView:
    id: int
    name: str
    inn: str | None
    values: dict[str, str]
    is_default: bool
    created_at: datetime
    updated_at: datetime


def to_view(organization: Organization) -> OrganizationView:
    return OrganizationView(
        id=organization.id,
        name=organization.name,
        inn=organization.inn,
        values=dict(organization.values),
        is_default=organization.is_default,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


def _clean(name: str, values: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    clean, errors = validate_requisites({**values, "name": name})
    if errors:
        raise ValidationError("; ".join(errors), code="organization.invalid")
    if not clean.get("name"):
        raise ValidationError("Название организации обязательно", code="organization.invalid")
    return clean["name"], clean


async def _owned(repo: OrganizationRepository, user_id: int, organization_id: int) -> Organization:
    organization = await repo.get(user_id, organization_id)
    if organization is None:
        raise NotFoundError("Организация не найдена", code="organization.not_found")
    return organization


async def list_organizations(session: AsyncSession, *, user_id: int) -> list[OrganizationView]:
    return [to_view(o) for o in await OrganizationRepository(session).list_for_user(user_id)]


async def create_organization(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    values: Mapping[str, str],
    is_default: bool = False,
) -> OrganizationView:
    clean_name, clean = _clean(name, values)
    repo = OrganizationRepository(session)
    inn = clean.get("inn")
    if inn and await repo.find_by_inn(user_id, inn) is not None:
        raise ValidationError(
            f"Организация с ИНН {inn} уже есть", code="organization.duplicate_inn"
        )
    first = await repo.get_default(user_id) is None
    organization = await repo.create(user_id, name=clean_name, inn=inn, values=clean)
    if first or is_default:
        await repo.make_default(organization)
    return to_view(organization)


async def update_organization(
    session: AsyncSession,
    *,
    user_id: int,
    organization_id: int,
    name: str,
    values: Mapping[str, str],
    is_default: bool = False,
) -> OrganizationView:
    repo = OrganizationRepository(session)
    organization = await _owned(repo, user_id, organization_id)
    clean_name, clean = _clean(name, values)
    inn = clean.get("inn")
    twin = await repo.find_by_inn(user_id, inn) if inn else None
    if twin is not None and twin.id != organization.id:
        raise ValidationError(
            f"Организация с ИНН {inn} уже есть", code="organization.duplicate_inn"
        )
    await repo.update(organization, name=clean_name, inn=inn, values=clean)
    if is_default:
        await repo.make_default(organization)
    return to_view(organization)


async def delete_organization(session: AsyncSession, *, user_id: int, organization_id: int) -> None:
    repo = OrganizationRepository(session)
    organization = await _owned(repo, user_id, organization_id)
    was_default = organization.is_default
    await repo.delete(organization)
    if was_default:
        rest = await repo.list_for_user(user_id)
        if rest:
            await repo.make_default(rest[0])


async def seller_for_document(
    session: AsyncSession, *, user_id: int, organization_id: int | None, strict: bool = True
) -> Organization | None:
    """Чьи реквизиты ставить продавцом: выбранная организация или основная.

    ``strict=False`` — для копии документа: его организацию могли удалить, и тогда
    копия идёт от основной, а не падает."""
    repo = OrganizationRepository(session)
    if organization_id is not None:
        organization = await repo.get(user_id, organization_id)
        if organization is not None:
            return organization
        if strict:
            raise NotFoundError("Организация не найдена", code="organization.not_found")
    return await repo.get_default(user_id)
