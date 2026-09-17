"""Вход по initData, ротация refresh-токена, детект повторного использования, выход."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import RefreshTokenRepository, UserRepository
from core.domain.exceptions import UnauthorizedError
from core.usecases.auth import (
    authenticate,
    decode_access_token,
    hash_refresh_token,
    login_with_init_data,
    logout,
    refresh_session,
)
from core.usecases.auth.config import AuthConfig

ADMINS = frozenset({777})


async def test_login_creates_user_and_tokens(
    session: AsyncSession, auth_config: AuthConfig, make_init_data
) -> None:
    result = await login_with_init_data(
        session,
        make_init_data(42, first_name="Ann", username="ann"),
        cfg=auth_config,
        admin_ids=ADMINS,
    )
    profile = result.profile
    assert profile.max_user_id == 42 and profile.username == "ann"
    assert profile.is_admin is False
    assert profile.last_login_at is not None
    claims = decode_access_token(auth_config, result.access_token)
    assert claims is not None and claims.user_id == profile.id
    stored = await RefreshTokenRepository(session).get_by_hash(
        hash_refresh_token(result.refresh_token)
    )
    assert stored is not None and stored.user_id == profile.id and stored.revoked_at is None


async def test_login_upserts_existing_user(
    session: AsyncSession, auth_config: AuthConfig, make_init_data
) -> None:
    first = await login_with_init_data(
        session, make_init_data(1, first_name="Old"), cfg=auth_config, admin_ids=ADMINS
    )
    second = await login_with_init_data(
        session, make_init_data(1, first_name="New"), cfg=auth_config, admin_ids=ADMINS
    )
    assert first.profile.id == second.profile.id
    assert second.profile.first_name == "New"
    assert await UserRepository(session).count() == 1


async def test_admin_flag_from_admin_ids(
    session: AsyncSession, auth_config: AuthConfig, make_init_data
) -> None:
    result = await login_with_init_data(
        session, make_init_data(777), cfg=auth_config, admin_ids=ADMINS
    )
    assert result.profile.is_admin is True
    claims = decode_access_token(auth_config, result.access_token)
    assert claims is not None and claims.is_admin is True
    profile = await authenticate(session, result.access_token, cfg=auth_config, admin_ids=ADMINS)
    assert profile.id == result.profile.id and profile.is_admin is True
    demoted = await authenticate(
        session, result.access_token, cfg=auth_config, admin_ids=frozenset()
    )
    assert demoted.is_admin is False, "админство берётся из актуального окружения, не из claims"


async def test_invalid_init_data_is_unauthorized(
    session: AsyncSession, auth_config: AuthConfig
) -> None:
    with pytest.raises(UnauthorizedError) as exc:
        await login_with_init_data(
            session, "auth_date=1&hash=bad", cfg=auth_config, admin_ids=ADMINS
        )
    assert exc.value.code == "auth.init_data.bad_signature"
    assert exc.value.status_code == 401


async def test_refresh_rotates_and_detects_reuse(
    session: AsyncSession, auth_config: AuthConfig, make_init_data
) -> None:
    login = await login_with_init_data(
        session, make_init_data(5), cfg=auth_config, admin_ids=ADMINS
    )
    rotated = await refresh_session(session, login.refresh_token, cfg=auth_config, admin_ids=ADMINS)
    assert rotated.refresh_token != login.refresh_token
    assert decode_access_token(auth_config, rotated.access_token) is not None

    # Старый токен уже ротирован: повторное предъявление — кража, семья отзывается целиком.
    with pytest.raises(UnauthorizedError) as exc:
        await refresh_session(session, login.refresh_token, cfg=auth_config, admin_ids=ADMINS)
    assert exc.value.code == "auth.refresh.reused"
    # Семья отозвана целиком: свежий токен больше не работает, но это уже не «кража».
    with pytest.raises(UnauthorizedError) as exc:
        await refresh_session(session, rotated.refresh_token, cfg=auth_config, admin_ids=ADMINS)
    assert exc.value.code == "auth.refresh.revoked"


async def test_refresh_unknown_and_expired(
    session: AsyncSession, auth_config: AuthConfig, make_init_data
) -> None:
    with pytest.raises(UnauthorizedError) as exc:
        await refresh_session(session, "no-such-token", cfg=auth_config, admin_ids=ADMINS)
    assert exc.value.code == "auth.refresh.unknown"

    login = await login_with_init_data(
        session, make_init_data(6), cfg=auth_config, admin_ids=ADMINS
    )
    later = datetime.now(UTC) + timedelta(seconds=auth_config.refresh_ttl_seconds + 1)
    with pytest.raises(UnauthorizedError) as exc:
        await refresh_session(
            session, login.refresh_token, cfg=auth_config, admin_ids=ADMINS, now=later
        )
    assert exc.value.code == "auth.refresh.expired"


async def test_logout_revokes_family(
    session: AsyncSession, auth_config: AuthConfig, make_init_data
) -> None:
    login = await login_with_init_data(
        session, make_init_data(8), cfg=auth_config, admin_ids=ADMINS
    )
    await logout(session, login.refresh_token)
    with pytest.raises(UnauthorizedError):
        await refresh_session(session, login.refresh_token, cfg=auth_config, admin_ids=ADMINS)
    # Повторный выход с уже отозванным токеном — не ошибка.
    await logout(session, login.refresh_token)
    await logout(session, "unknown")


async def test_authenticate_rejects_bad_token_and_missing_user(
    session: AsyncSession, auth_config: AuthConfig
) -> None:
    with pytest.raises(UnauthorizedError) as exc:
        await authenticate(session, "garbage", cfg=auth_config, admin_ids=ADMINS)
    assert exc.value.code == "auth.invalid_token"
    from core.usecases.auth import issue_access_token

    orphan = issue_access_token(auth_config, user_id=10**6, is_admin=False)
    with pytest.raises(UnauthorizedError) as exc:
        await authenticate(session, orphan, cfg=auth_config, admin_ids=ADMINS)
    assert exc.value.code == "auth.unknown_user"


async def test_login_purges_expired_tokens_of_the_user(
    session: AsyncSession, auth_config: AuthConfig, make_init_data
) -> None:
    first = await login_with_init_data(
        session, make_init_data(9), cfg=auth_config, admin_ids=ADMINS
    )
    # Второй вход «через месяц»: initData подписан той же будущей датой, иначе он протухший.
    later = datetime.now(UTC) + timedelta(seconds=auth_config.refresh_ttl_seconds + 60)
    await login_with_init_data(
        session,
        make_init_data(9, auth_date=int(later.timestamp())),
        cfg=auth_config,
        admin_ids=ADMINS,
        now=later,
    )
    assert (
        await RefreshTokenRepository(session).get_by_hash(hash_refresh_token(first.refresh_token))
        is None
    )
