"""Wire-формы шаблонов, документов и справочников: контракт мини-аппа и бота."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.domain.documents import FieldType, ValueSource


class FieldSpecSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    type: FieldType
    required: bool
    group: str
    hint: str
    max_length: int | None


class TemplateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    kind: str
    description: str
    body_format: str
    is_builtin: bool
    fields: list[FieldSpecSchema]


class FieldValueSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: str
    source: ValueSource = ValueSource.MANUAL
    confidence: float | None = Field(default=None, ge=0, le=1)
    confirmed: bool = True


class FieldErrorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    code: str
    message: str


class DocumentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str
    template: TemplateSchema
    counterparty_id: int | None
    values: dict[str, FieldValueSchema]
    errors: list[FieldErrorSchema]
    missing: list[str] = Field(description="Обязательные поля, которые ещё не заполнены")
    unconfirmed: list[str] = Field(
        description="Распознанное и предложенное агентом без подтверждения"
    )
    ready: bool
    preview: str
    created_at: datetime
    updated_at: datetime


class DocumentSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str
    template_title: str
    counterparty_name: str | None
    updated_at: datetime


class DocumentFileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    format: str
    filename: str
    size: int
    sha256: str
    stale: bool = Field(description="Файл собран до последней правки полей")
    created_at: datetime
    updated_at: datetime


class RenderRequest(BaseModel):
    format: Literal["docx", "pdf"] = "docx"


class SendDocumentResponse(BaseModel):
    event_id: str = Field(description="UUID события доставки; он же в логах бота")
    format: str
    filename: str


class CreateDocumentRequest(BaseModel):
    template_id: int
    counterparty_id: int | None = None
    title: str = Field(default="", max_length=255)


class SetFieldsRequest(BaseModel):
    values: dict[str, FieldValueSchema] = Field(
        description="Ключ поля → значение; пустая строка стирает поле"
    )
    title: str | None = Field(default=None, max_length=255)


class CounterpartySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    inn: str | None
    values: dict[str, str]
    created_at: datetime
    updated_at: datetime


class CounterpartyRequest(BaseModel):
    name: str = Field(max_length=255)
    values: dict[str, str] = Field(default_factory=dict)


class CompanyProfileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    values: dict[str, str]


class CompanyProfileRequest(BaseModel):
    name: str = Field(max_length=255)
    values: dict[str, str] = Field(default_factory=dict)
