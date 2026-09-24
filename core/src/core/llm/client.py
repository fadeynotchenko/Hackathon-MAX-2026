"""Порт языковой модели: то, что сценарии знают о модели, без деталей провайдера.

Два вида вызова: обычный текст (ответ на вопрос, сопроводительное письмо) и
JSON по схеме (значения полей документа). К сообщению можно приложить файл —
фото, скан или голосовое: сценарий отдаёт байты, а как они попадут к
провайдеру (хранилище файлов, base64 в теле запроса), решает адаптер.

Ошибки делятся на временные — провайдер недоступен, переполнен или не пустил —
на отказ принять вход (формат или размер файла) и на плохой ответ: сценарию
нужно по-разному сказать о них пользователю.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Attachment:
    """Файл к сообщению. Байты не попадают в repr: объект оказывается в логах и трейсах."""

    data: bytes = field(repr=False)
    media_type: str
    filename: str


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    attachments: tuple[Attachment, ...] = ()


class LLMError(RuntimeError):
    """Модель ответила, но ответ нельзя использовать."""


class LLMUnavailableError(LLMError):
    """Провайдер недоступен: сеть, таймаут, лимит запросов, авторизация."""


class LLMInputError(LLMError):
    """Провайдер не принял вход: формат или размер приложенного файла."""


class LLMClient(Protocol):
    async def complete(
        self, messages: Sequence[ChatMessage], *, max_tokens: int | None = None
    ) -> str: ...

    async def complete_json(
        self, messages: Sequence[ChatMessage], *, schema: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...
