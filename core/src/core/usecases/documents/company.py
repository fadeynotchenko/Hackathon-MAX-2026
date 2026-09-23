"""Реквизиты пользователя: подставляются в документ как сторона продавца."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import CompanyProfileRepository
from core.domain.exceptions import ValidationError
from core.usecases.documents.requisites import validate_requisites


@dataclass(frozen=True)
class CompanyProfileView:
    name: str
    values: dict[str, str]


async def get_company_profile(session: AsyncSession, *, user_id: int) -> CompanyProfileView:
    profile = await CompanyProfileRepository(session).get(user_id)
    if profile is None:
        return CompanyProfileView(name="", values={})
    return CompanyProfileView(name=profile.name, values=dict(profile.values))


async def save_company_profile(
    session: AsyncSession, *, user_id: int, name: str, values: Mapping[str, str]
) -> CompanyProfileView:
    clean, errors = validate_requisites({**values, "name": name})
    if errors:
        raise ValidationError("; ".join(errors), code="company.invalid")
    profile = await CompanyProfileRepository(session).upsert(
        user_id, name=clean.get("name", name.strip()), values=clean
    )
    return CompanyProfileView(name=profile.name, values=dict(profile.values))
