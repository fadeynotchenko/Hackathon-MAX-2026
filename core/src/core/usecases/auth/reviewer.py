"""Доступ для проверяющих: долгий токен отдельной тестовой учётки.

Обычный вход идёт через initData, подписанный клиентом MAX, а access-токен живёт
15 минут и продлевается refresh-cookie из браузера. У внешнего проверяющего нет
ни клиента MAX, ни браузера: выданный ему обычный токен истёк бы до начала
проверки. Поэтому оператор выпускает токен сам (``core.scripts.issue_reviewer_token``)
— только для отдельной учётки и не дольше ``MAX_REVIEWER_DAYS``.

Отзыв — удаление учётки: ``authenticate`` читает пользователя на каждый запрос,
поэтому токен удалённой учётки перестаёт работать сразу.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import UserRepository, UserUpsert
from core.logs import biz_info
from core.usecases.auth.config import AuthConfig
from core.usecases.auth.tokens import issue_access_token

logger = logging.getLogger(__name__)

# Учётка проверяющих по умолчанию: выдуманный MAX-id с номером команды. Файлы в чат
# ей не доставить; чтобы получать их, выпускайте токен на свой настоящий MAX-id.
REVIEWER_MAX_USER_ID = 409_000_001
MAX_REVIEWER_DAYS = 30


@dataclass(frozen=True)
class ReviewerAccess:
    user_id: int
    max_user_id: int
    access_token: str
    expires_at: datetime


async def issue_reviewer_access(
    session: AsyncSession,
    *,
    cfg: AuthConfig,
    days: int,
    max_user_id: int = REVIEWER_MAX_USER_ID,
    first_name: str = "Проверяющий",
    now: datetime | None = None,
) -> ReviewerAccess:
    if not 1 <= days <= MAX_REVIEWER_DAYS:
        raise ValueError(f"срок доступа — от 1 до {MAX_REVIEWER_DAYS} дней")
    current = now or datetime.now(UTC)
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(max_user_id=max_user_id, first_name=first_name, via="reviewer"),
        touch_login=False,
        now=current,
    )
    ttl = timedelta(days=days)
    token = issue_access_token(
        cfg,
        user_id=user.id,
        is_admin=False,
        now=current,
        ttl_seconds=int(ttl.total_seconds()),
    )
    biz_info(
        logger,
        "auth.reviewer.issued",
        user_id=user.id,
        max_user_id=max_user_id,
        expires_at=(current + ttl).isoformat(),
    )
    return ReviewerAccess(user.id, max_user_id, token, current + ttl)


async def revoke_reviewer_access(
    session: AsyncSession, *, max_user_id: int = REVIEWER_MAX_USER_ID
) -> bool:
    """Удалить учётку проверяющих вместе с её документами: токены умирают сразу."""
    users = UserRepository(session)
    user = await users.get_by_max_id(max_user_id)
    if user is None:
        return False
    await users.delete(user.id)
    biz_info(logger, "auth.reviewer.revoked", user_id=user.id, max_user_id=max_user_id)
    return True
