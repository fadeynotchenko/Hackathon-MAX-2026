"""Контракты событий между ядром и ботом — единственный источник правды по payload.

Каждое событие — pydantic-модель: ядро публикует ``model_dump()``, потребитель
делает ``model_validate(event.payload)`` и падает на первом несоответствии.
JSON Schema этих моделей экспортируется в ``contracts/events.schema.json``
(``uv run python -m core.scripts.export_event_schemas``), и zod-схемы бота
сверяются с ней тестом: дрейф поля ловится до прода, а не в нём.

Версия конверта (``Event.v``) меняется только при несовместимой правке: тогда
рядом появляется ``NotifyUserV2``, а старая модель живёт, пока не обновлён
последний потребитель. Добавление необязательного поля версию не меняет.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ENVELOPE_VERSION = 1

# Имена событий: <источник>.<что_случилось>.
NOTIFY_USER = "notify.user"
DOCUMENT_READY = "document.ready"
BOT_USER_STARTED = "bot.user_started"


class EventPayload(BaseModel):
    """Базовый класс: лишние поля запрещены, чтобы опечатка в имени не прошла молча."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class NotifyUser(EventPayload):
    """Ядро → бот: отправить пользователю сообщение в MAX."""

    max_user_id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=4000)
    format: Literal["markdown", "html"] | None = None


class DocumentReady(EventPayload):
    """Ядро → бот: отдать пользователю готовый файл документа.

    Байты в событие не кладутся: стрим — не файловое хранилище. Вместо них
    одноразовый ``download_token``, по которому бот забирает файл у ядра.
    """

    max_user_id: int = Field(gt=0)
    document_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=255)
    format: Literal["docx", "pdf"]
    size: int = Field(gt=0)
    download_token: str = Field(min_length=16, max_length=128)
    text: str = Field(min_length=1, max_length=4000)


class BotUserStarted(EventPayload):
    """Бот → ядро: пользователь нажал «Начать» (update bot_started)."""

    max_user_id: int = Field(gt=0)
    chat_id: int
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    start_payload: str | None = None


# Реестр: имя события → модель payload. Используется экспортом схем и тестами.
EVENT_PAYLOADS: dict[str, type[EventPayload]] = {
    NOTIFY_USER: NotifyUser,
    DOCUMENT_READY: DocumentReady,
    BOT_USER_STARTED: BotUserStarted,
}
