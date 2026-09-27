"""Wire-формы шаблонов, документов и справочников: контракт мини-аппа и бота."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.api.schemas.common import DbId, PrintableStr
from core.domain.documents import FieldType, ValueSource


class PlaceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    text: str = Field(description="Фрагмент файла-образца, на месте которого встанет значение")
    before: str = Field(
        default="", description="Текст перед фрагментом в той же строке: уточняет, какой он"
    )


class FieldSpecSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    type: FieldType
    required: bool
    group: str
    hint: str
    max_length: int | None
    carry_over: bool = Field(
        default=True, description="Значение переносится в копию документа (номер и даты — нет)"
    )
    today_by_default: bool = Field(
        default=False, description="Пустая дата при создании документа — сегодняшняя"
    )
    places: list[PlaceSchema] = Field(
        default_factory=list, description="Места значения в файле-образце; у текстовых — пусто"
    )


class TemplateFileSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    text: str | None = Field(
        default=None,
        description="Текст образца, строка на абзац; только в ответе на один шаблон",
    )


class TemplateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    kind: str = Field(description="Вид документа: invoice, offer, contract или other")
    description: str
    body_format: str
    is_builtin: bool
    fields: list[FieldSpecSchema]
    body: str = Field(description="Текст шаблона с маркерами {{key}} на месте полей")
    preview: str = Field(description="Текст пустого бланка — предпросмотр до заполнения")
    file: TemplateFileSchema | None = Field(
        default=None, description="Файл-образец DOCX: документ собирается в его оформлении"
    )


class PlaceRequest(BaseModel):
    text: PrintableStr = Field(min_length=1, max_length=300)
    before: PrintableStr = Field(default="", max_length=100)


class TemplateFieldRequest(BaseModel):
    key: str = Field(
        min_length=1,
        max_length=48,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Ключ маркера в тексте; seller_* и client_* — реквизиты сторон",
    )
    label: PrintableStr = Field(max_length=100)
    type: FieldType = FieldType.TEXT
    required: bool = True
    hint: PrintableStr = Field(default="", max_length=200)
    carry_over: bool = True
    today_by_default: bool = False
    places: list[PlaceRequest] = Field(
        default_factory=list,
        max_length=20,
        description="Где в файле-образце стоит значение; только вместе с file_id",
    )


TemplateKind = Literal["invoice", "offer", "contract", "other"]


class TemplateRequest(BaseModel):
    title: PrintableStr = Field(max_length=64)
    kind: TemplateKind = Field(
        default="other", description="Вид документа: счёт, КП, договор или другой"
    )
    description: PrintableStr = Field(default="", max_length=300)
    body: PrintableStr = Field(
        default="",
        max_length=20000,
        description="Текст с маркерами {{key}}; каждый маркер описан в fields. "
        "С file_id не нужен: текст собирается из образца",
    )
    fields: list[TemplateFieldRequest] = Field(max_length=50)
    file_id: DbId | None = Field(
        default=None, description="Файл-образец DOCX из POST /templates/import"
    )


class ImportedFieldSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str = Field(description="Ключ каталога (реквизит, number, date, total); пусто — своё поле")
    label: str
    type: FieldType
    required: bool
    places: list[PlaceSchema]


class TemplateImportSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: int | None = Field(
        description="Сохранённый образец DOCX; у PDF пусто — шаблон будет текстовым"
    )
    filename: str
    format: Literal["docx", "pdf"]
    title: str = Field(description="Предложенное название шаблона")
    text: str = Field(description="Текст файла, строка на абзац")
    fields: list[ImportedFieldSchema] = Field(description="Найденные места для данных")
    found_by: Literal["markers", "assistant", "none"] = Field(
        description="Кто нашёл места: метки {{…}} в файле, помощник или никто"
    )
    notice: str | None = Field(description="Почему места не искались помощником")
    kind: TemplateKind = Field(description="Вид документа по мнению помощника или по заголовку")


class FieldValueSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: str
    source: ValueSource = ValueSource.MANUAL
    confidence: float | None = Field(default=None, ge=0, le=1)
    confirmed: bool = True
    fragment: PrintableStr | None = Field(
        default=None,
        max_length=500,
        description="Строка с фото или скана, откуда прочитано значение",
    )


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
    organization_id: int | None = Field(
        description="Своя организация, чьи реквизиты стоят продавцом"
    )
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


class SendStateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sent_at: datetime = Field(description="Когда файл последний раз отправлен в чат")
    format: str | None
    delivery: Literal["pending", "delivered", "failed"] = Field(
        description="Чем кончилась доставка: бот ещё не ответил, файл в чате, не доставлен"
    )


class DocumentSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str
    template_title: str
    counterparty_name: str | None
    client: str | None = Field(description="Кому: карточка контрагента или название клиента")
    number: str | None = Field(
        default=None, description="Номер документа из полей: отличает одинаковые счета в архиве"
    )
    updated_at: datetime
    created_at: datetime
    sent: SendStateSchema | None = Field(description="Последняя отправка; пусто — не отправлялся")


class DocumentFactSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: Literal[
        "created", "ready", "rendered", "sent", "delivered", "delivery_failed", "rejected"
    ]
    format: str | None
    code: str | None = Field(description="Код отказа: отклонённое значение или недоставка")
    source: str | None = Field(description="Источник отклонённого значения; copy у копии")
    at: datetime


class CopyDocumentRequest(BaseModel):
    title: PrintableStr | None = Field(
        default=None, max_length=255, description="Название копии; пусто — как у исходного"
    )


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


class SendDocumentRequest(RenderRequest):
    text: PrintableStr | None = Field(
        default=None,
        max_length=4000,
        description="Сопроводительный текст; пусто — служебный текст по умолчанию",
    )


class ConfirmFieldsRequest(BaseModel):
    keys: list[str] | None = Field(
        default=None,
        description="Какие поля подтвердить; null — все ждущие подтверждения, [] — ни одного",
    )


class SendDocumentResponse(BaseModel):
    event_id: str = Field(description="UUID события доставки; он же в логах бота")
    format: str
    filename: str


class CreateDocumentRequest(BaseModel):
    template_id: DbId
    counterparty_id: DbId | None = None
    organization_id: DbId | None = Field(
        default=None, description="От какой своей организации; пусто — от основной"
    )
    title: PrintableStr = Field(default="", max_length=255)


class SetFieldsRequest(BaseModel):
    values: dict[str, FieldValueSchema] = Field(
        description="Ключ поля → значение; пустая строка стирает поле"
    )
    title: PrintableStr | None = Field(default=None, max_length=255)


class AgentFillRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AgentFillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reply: str = Field(description="Ответ помощника для показа в чате")
    filled: list[str] = Field(description="Поля, которые помощник заполнил")
    rejected: list[FieldErrorSchema] = Field(
        description="Предложенные значения, не прошедшие проверку"
    )
    document: DocumentSchema


class VoiceFillResponse(AgentFillResponse):
    transcript: str = Field(description="Что помощник расслышал в голосовом")


class RecognizedRequisitesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str = Field(description="Что во вложении: «карточка предприятия», «счёт на оплату»")
    values: dict[str, FieldValueSchema] = Field(
        description="Реквизит → значение с фрагментом; ничего не сохранено"
    )
    errors: list[FieldErrorSchema] = Field(
        description="Прочитанные значения, не прошедшие проверку реквизитов"
    )


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AgentTextResponse(BaseModel):
    text: str


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


class OrganizationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    inn: str | None
    values: dict[str, str]
    is_default: bool = Field(description="Основная: от неё документ, если организацию не выбрали")
    created_at: datetime
    updated_at: datetime


class OrganizationRequest(BaseModel):
    name: str = Field(max_length=255)
    values: dict[str, str] = Field(default_factory=dict)
    is_default: bool = Field(default=False, description="Сделать основной")
