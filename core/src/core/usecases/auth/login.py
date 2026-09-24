"""Вход через initData мини-аппа: подпись → пользователь в БД → сессия."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import RefreshTokenRepository, UserRepository, UserUpsert
from core.domain.exceptions import UnauthorizedError
from core.domain.initdata import InitDataError, validate_init_data
from core.logs import biz_info, biz_warn
from core.usecases.auth.config import AuthConfig
from core.usecases.auth.session import IssuedSession, issue_session
from core.usecases.users.activity import mark_active

logger = logging.getLogger(__name__)


async def login_with_init_data(
    session: AsyncSession,
    raw_init_data: str,
    *,
    cfg: AuthConfig,
    admin_ids: frozenset[int],
    now: datetime | None = None,
) -> IssuedSession:
    """Проверить initData и выдать сессию. Невалидные данные — 401 с кодом причины."""
    current = now or datetime.now(UTC)
    try:
        init_data = validate_init_data(
            raw_init_data,
            cfg.bot_token,
            max_age_seconds=cfg.init_data_max_age_seconds,
            now=current.timestamp(),
        )
    except InitDataError as exc:
        biz_warn(logger, "auth.login.rejected", reason=exc.code)
        raise UnauthorizedError(
            "Не удалось подтвердить данные запуска мини-приложения",
            code=f"auth.init_data.{exc.code}",
            log_message=str(exc),
        ) from exc

    max_user = init_data.user
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(
            max_user_id=max_user.id,
            first_name=max_user.first_name,
            last_name=max_user.last_name,
            username=max_user.username,
            language_code=max_user.language_code,
            photo_url=max_user.photo_url,
            via="mini_app",
        ),
        touch_login=True,
        now=current,
    )
    # Вход — естественный момент подчистить мусор этого же пользователя.
    await RefreshTokenRepository(session).delete_expired_for_user(user.id, before=current)
    await mark_active(session, user.id, now=current)
    issued = await issue_session(
        session, user, cfg=cfg, admin_ids=admin_ids, family_id=str(uuid.uuid4()), now=current
    )
    biz_info(
        logger,
        "auth.login.ok",
        user_id=user.id,
        max_user_id=max_user.id,
        is_admin=issued.profile.is_admin,
        start_param=init_data.start_param,
    )
    return issued
