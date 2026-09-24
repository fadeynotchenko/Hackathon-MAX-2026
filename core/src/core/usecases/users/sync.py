"""Пользователи, пришедшие через бота (событие bot.user_started), а не мини-апп."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import UserRepository, UserUpsert
from core.events.contracts import BotUserStarted
from core.logs import biz_info
from core.usecases.users.activity import mark_active

logger = logging.getLogger(__name__)


async def register_user_from_bot(
    session: AsyncSession, data: BotUserStarted, *, now: datetime | None = None
) -> int:
    """Создать или обновить пользователя по данным бота. Возвращает внутренний id.

    Идемпотентно: повторная доставка того же события даёт тот же результат.
    Аватар бот не знает, поэтому его не трогает (UserUpsert.photo_url = KEEP).
    """
    current = now or datetime.now(UTC)
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(
            max_user_id=data.max_user_id,
            first_name=data.first_name,
            last_name=data.last_name,
            username=data.username,
            language_code=data.language_code,
            via="bot",
        ),
        touch_login=False,
        now=current,
    )
    await mark_active(session, user.id, now=current)
    biz_info(
        logger,
        "users.synced_from_bot",
        user_id=user.id,
        max_user_id=data.max_user_id,
        start_payload=data.start_payload,
    )
    return user.id
