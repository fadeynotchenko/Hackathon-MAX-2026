from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AdminStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    users_total: int
    users_active_24h: int


class NotifyRequest(BaseModel):
    max_user_id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=4000)
    format: Literal["markdown", "html"] | None = None


class NotifyResponse(BaseModel):
    event_id: str = Field(
        description="UUID события: тот же event_id, что в логах ядра (events.published) и бота"
    )
