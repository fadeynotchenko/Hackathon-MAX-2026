from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserProfileSchema(BaseModel):
    """Wire-форма core.usecases.users.UserProfile (from_attributes): OpenAPI-контракт для мини-аппа."""

    model_config = ConfigDict(from_attributes=True)

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
