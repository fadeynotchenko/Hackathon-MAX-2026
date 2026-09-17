from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.api.schemas.user import UserProfileSchema


class MaxLoginRequest(BaseModel):
    init_data: str = Field(
        min_length=1,
        max_length=8192,
        description="Строка window.WebApp.initData как есть, без разбора на клиенте",
    )


class SessionResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 — тип токена, не секрет
    expires_in: int = Field(description="Время жизни access-токена в секундах")
    user: UserProfileSchema
