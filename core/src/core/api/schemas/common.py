"""Схемы, общие для всех роутеров."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from fastapi import Path
from pydantic import AfterValidator, BaseModel, Field

# id в базе — BIGINT: число больше роняло драйвер в 500, теперь это 422.
MAX_DB_ID = 2**63 - 1
IdPath = Annotated[int, Path(ge=1, le=MAX_DB_ID)]
DbId = Annotated[int, Field(ge=1, le=MAX_DB_ID)]

_UNPRINTABLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200d\u2060\ufeff]")


def _printable(text: str) -> str:
    """Служебные символы из свободного текста — прочь: NUL не принимает
    PostgreSQL, остальные ломают сборку DOCX, невидимые делают пустое непустым."""
    return _UNPRINTABLE.sub("", text)


PrintableStr = Annotated[str, AfterValidator(_printable)]


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
