"""Выдача, продление и отзыв сессии мини-аппа.

Сессия = короткоживущий access-JWT + opaque refresh-токен, хранящийся в БД
хешем. Ротация: старый refresh отзывается, выдаётся новый в той же семье.
Повторное предъявление уже ротированного токена — признак украденной копии:
семья отзывается целиком, и легитимный клиент тоже перелогинится.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import RefreshToken, User
from core.db.repositories import RefreshTokenRepository, UserRepository
from core.domain.exceptions import UnauthorizedError
from core.logs import biz_info, biz_warn
from core.usecases.auth.config import AuthConfig
from core.usecases.auth.tokens import (
    decode_access_token,
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
    refresh_expiry,
)
from core.usecases.users.profile import UserProfile, build_profile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssuedSession:
    """Результат входа и продления: то, что API отдаёт клиенту."""

    profile: UserProfile
    access_token: str
    refresh_token: str
    refresh_expires_at: datetime


async def issue_session(
    session: AsyncSession,
    user: User,
    *,
    cfg: AuthConfig,
    admin_ids: frozenset[int],
    family_id: str,
    now: datetime,
) -> IssuedSession:
    """Единственное место, где рождается пара токенов (общая часть входа и продления)."""
    profile = build_profile(user, admin_ids=admin_ids)
    refresh_token = new_refresh_token()
    expires_at = refresh_expiry(cfg, now)
    await RefreshTokenRepository(session).create(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_token),
        family_id=family_id,
        expires_at=expires_at,
    )
    return IssuedSession(
        profile=profile,
        access_token=issue_access_token(cfg, user_id=user.id, is_admin=profile.is_admin, now=now),
        refresh_token=refresh_token,
        refresh_expires_at=expires_at,
    )


async def _reject_reused(
    session: AsyncSession, tokens: RefreshTokenRepository, stored: RefreshToken, *, now: datetime
) -> None:
    """Повторное предъявление ротированного токена: отозвать семью и ответить 401.

    Отзыв коммитится здесь явно: запрос завершается исключением, а единица
    работы (core.db.base.get_session) на исключении делает rollback — без
    commit защита существовала бы только в логе."""
    revoked = await tokens.revoke_family(stored.family_id, now=now)
    await session.commit()
    biz_warn(logger, "auth.refresh.reuse_detected", user_id=stored.user_id, revoked=revoked)
    raise UnauthorizedError("Сессия отозвана", code="auth.refresh.reused")


async def _stored_refresh_token(
    session: AsyncSession, tokens: RefreshTokenRepository, raw_refresh_token: str, *, now: datetime
) -> RefreshToken:
    stored = await tokens.get_by_hash(hash_refresh_token(raw_refresh_token))
    if stored is None:
        raise UnauthorizedError("Сессия не найдена", code="auth.refresh.unknown")
    if stored.replaced_by_hash is not None:
        await _reject_reused(session, tokens, stored, now=now)
    if stored.revoked_at is not None:
        # Отозван выходом или отзывом семьи, а не ротацией: это не кража, просто
        # клиент с устаревшей cookie (например, веб-клиент MAX после logout).
        raise UnauthorizedError("Сессия завершена", code="auth.refresh.revoked")
    if stored.expires_at <= now:
        raise UnauthorizedError("Сессия истекла", code="auth.refresh.expired")
    return stored


async def refresh_session(
    session: AsyncSession,
    raw_refresh_token: str,
    *,
    cfg: AuthConfig,
    admin_ids: frozenset[int],
    now: datetime | None = None,
) -> IssuedSession:
    current = now or datetime.now(UTC)
    tokens = RefreshTokenRepository(session)
    stored = await _stored_refresh_token(session, tokens, raw_refresh_token, now=current)
    user = await UserRepository(session).get_by_id(stored.user_id)
    if user is None:
        raise UnauthorizedError("Пользователь не найден", code="auth.refresh.no_user")

    issued = await issue_session(
        session, user, cfg=cfg, admin_ids=admin_ids, family_id=stored.family_id, now=current
    )
    rotated = await tokens.mark_rotated(
        stored, replaced_by_hash=hash_refresh_token(issued.refresh_token), now=current
    )
    if not rotated:
        # Параллельный запрос успел ротировать этот же токен первым.
        await _reject_reused(session, tokens, stored, now=current)
    biz_info(logger, "auth.refresh.ok", user_id=user.id)
    return issued


async def authenticate(
    session: AsyncSession, access_token: str, *, cfg: AuthConfig, admin_ids: frozenset[int]
) -> UserProfile:
    """Bearer-токен → профиль. Пользователь читается из БД на каждый запрос: токен
    живёт 15 минут, но удалённый аккаунт должен терять доступ сразу. Админство
    берётся из актуального окружения, а не из claims: снятие прав действует сразу."""
    claims = decode_access_token(cfg, access_token)
    if claims is None:
        raise UnauthorizedError("Токен недействителен или истёк", code="auth.invalid_token")
    user = await UserRepository(session).get_by_id(claims.user_id)
    if user is None:
        raise UnauthorizedError("Пользователь не найден", code="auth.unknown_user")
    return build_profile(user, admin_ids=admin_ids)


async def logout(
    session: AsyncSession, raw_refresh_token: str, *, now: datetime | None = None
) -> None:
    """Выход отзывает всю семью токена: одна кнопка «выйти» закрывает все копии сессии."""
    current = now or datetime.now(UTC)
    tokens = RefreshTokenRepository(session)
    stored = await tokens.get_by_hash(hash_refresh_token(raw_refresh_token))
    if stored is None:
        return
    await tokens.revoke_family(stored.family_id, now=current)
    biz_info(logger, "auth.logout", user_id=stored.user_id)
