"""Доступ для проверяющих: долгий токен отдельной учётки, отзыв удалением учётки."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import UserRepository
from core.domain.exceptions import UnauthorizedError
from core.usecases.auth import (
    REVIEWER_MAX_USER_ID,
    AuthConfig,
    authenticate,
    decode_access_token,
    issue_reviewer_access,
    revoke_reviewer_access,
)


async def test_reviewer_token_outlives_a_regular_session(
    session: AsyncSession, auth_config: AuthConfig
) -> None:
    # Время настоящее: PyJWT отвергает токен, выпущенный «в будущем».
    now = datetime.now(UTC).replace(microsecond=0)
    access = await issue_reviewer_access(session, cfg=auth_config, days=14, now=now)

    claims = decode_access_token(auth_config, access.access_token)
    assert claims is not None and claims.expires_at == now + timedelta(days=14)
    assert access.max_user_id == REVIEWER_MAX_USER_ID
    user = await UserRepository(session).get_by_max_id(REVIEWER_MAX_USER_ID)
    assert user is not None and user.first_seen_via == "reviewer"

    again = await issue_reviewer_access(session, cfg=auth_config, days=1, now=now)
    assert again.user_id == access.user_id, "повторная выдача — та же учётка"


async def test_revoke_kills_the_token_at_once(
    session: AsyncSession, auth_config: AuthConfig
) -> None:
    access = await issue_reviewer_access(session, cfg=auth_config, days=14)
    profile = await authenticate(
        session, access.access_token, cfg=auth_config, admin_ids=frozenset()
    )
    assert profile.id == access.user_id and not profile.is_admin

    assert await revoke_reviewer_access(session)
    assert not await revoke_reviewer_access(session)
    with pytest.raises(UnauthorizedError):
        await authenticate(session, access.access_token, cfg=auth_config, admin_ids=frozenset())


@pytest.mark.parametrize("days", [0, 31])
async def test_term_is_bounded(session: AsyncSession, auth_config: AuthConfig, days: int) -> None:
    with pytest.raises(ValueError):
        await issue_reviewer_access(session, cfg=auth_config, days=days)


async def test_reviewer_token_works_against_the_api(
    app, client: AsyncClient, session: AsyncSession, auth_config: AuthConfig
) -> None:
    access = await issue_reviewer_access(session, cfg=auth_config, days=14)
    await session.commit()

    response = await client.get(
        "/api/v1/templates", headers={"Authorization": f"Bearer {access.access_token}"}
    )
    assert response.status_code == 200
