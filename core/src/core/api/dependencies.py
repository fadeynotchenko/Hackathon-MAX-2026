"""Зависимости FastAPI: сессия БД, текущий пользователь, проверка админа."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.state import ApiState, api_state
from core.db import get_redis
from core.db.base import get_session
from core.domain.exceptions import ForbiddenError, UnauthorizedError
from core.logs import bind_context
from core.usecases.auth import authenticate
from core.usecases.users import UserProfile

StateDep = Annotated[ApiState, Depends(api_state)]


async def db_session() -> AsyncIterator[AsyncSession]:
    """Одна сессия на запрос; commit/rollback делает get_session."""
    async with get_session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(db_session)]


def redis_client() -> Redis:
    return get_redis()


RedisDep = Annotated[Redis, Depends(redis_client)]


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def current_user(request: Request, state: StateDep, session: SessionDep) -> UserProfile:
    token = _bearer_token(request)
    if token is None:
        raise UnauthorizedError("Требуется авторизация", code="auth.missing_token")
    profile = await authenticate(
        session, token, cfg=state.auth_config, admin_ids=state.app_config.admin_max_ids
    )
    bind_context(user_id=profile.id)
    return profile


CurrentUserDep = Annotated[UserProfile, Depends(current_user)]


async def admin_user(current: CurrentUserDep) -> UserProfile:
    if not current.is_admin:
        raise ForbiddenError("Недостаточно прав", code="auth.not_admin")
    return current


AdminDep = Annotated[UserProfile, Depends(admin_user)]
