"""Профиль пользователя — выход слоя use-case-ов.

ORM-объект ``core.db.models.User`` за пределы usecases не выходит: API и джобы
получают этот frozen dataclass. Здесь же единственное место, где решается,
кто администратор (по списку ``ADMIN_MAX_IDS`` из окружения).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.db.models import User


@dataclass(frozen=True)
class UserProfile:
    id: int
    max_user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    display_name: str
    language_code: str | None
    photo_url: str | None
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None


def build_profile(user: User, *, admin_ids: frozenset[int]) -> UserProfile:
    return UserProfile(
        id=user.id,
        max_user_id=user.max_user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        display_name=user.display_name,
        language_code=user.language_code,
        photo_url=user.photo_url,
        is_admin=user.max_user_id in admin_ids,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
