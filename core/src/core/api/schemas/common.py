"""Схемы, общие для всех роутеров."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str = Field(description="Текст для показа пользователю")
    code: str = Field(description="Машинный код ошибки, например auth.invalid_token")
    request_id: str | None = Field(
        default=None, description="Идентификатор запроса для поиска в логах"
    )
    errors: list[dict[str, Any]] | None = Field(
        default=None, description="Подробности ошибки валидации (422)"
    )


class OkResponse(BaseModel):
    ok: Literal[True] = True


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str] = Field(description="Компонент → ok | текст ошибки")
