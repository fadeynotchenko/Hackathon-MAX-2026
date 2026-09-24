from __future__ import annotations

from datetime import date
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


class DailyMetricsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date = Field(description="День по Москве")
    users_total: int
    users_new: int
    active_day: int
    active_week: int = Field(description="Уникальные активные за семь дней по этот день")
    documents_created: int
    documents_copied: int = Field(description="Созданные на основе прошлого документа")
    created_by_kind: dict[str, int] = Field(description="Вид шаблона → создано документов")
    rendered_docx: int
    rendered_pdf: int
    sent: int
    delivered: int
    delivery_failed: int
    rejected: int = Field(description="Значения, которые проверка остановила")


class FunnelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created: int
    ready: int
    rendered: int
    sent: int
    delivered: int


class AutofillSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    by_source: dict[str, int] = Field(description="Источник значения → полей")
    total: int
    automatic_share: float | None = Field(description="Доля полей, заполненных не руками")


class DistributionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    count: int
    median: float | None
    p90: float | None


class DeliveriesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivered: int
    failed: int
    pending: int = Field(description="Отправлены в периоде, бот ещё не подтвердил")


class AdminMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    since: date
    until: date
    daily: list[DailyMetricsSchema]
    funnel: FunnelSchema = Field(description="Документы периода по шагам до доставки")
    autofill: AutofillSchema
    rejections: dict[str, int] = Field(description="Код ошибки → сколько раз поймана")
    deliveries: DeliveriesSchema
    time_to_send_minutes: DistributionSchema = Field(
        description="От создания документа до первой отправки в чат"
    )
    render_ms: dict[str, DistributionSchema] = Field(description="Формат → время сборки файла")
