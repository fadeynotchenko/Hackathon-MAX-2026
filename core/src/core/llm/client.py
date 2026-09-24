"""Порт языковой модели: то, что сценарии знают о модели, без деталей провайдера.

Два вида вызова: обычный текст (ответ на вопрос, сопроводительное письмо) и
JSON по схеме (значения полей документа). Ошибки делятся на временные —
провайдер недоступен, переполнен или не пустил — и на плохой ответ: сценарию
нужно по-разному сказать о них пользователю.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


class LLMError(RuntimeError):
    """Модель ответила, но ответ нельзя использовать."""


class LLMUnavailableError(LLMError):
    """Провайдер недоступен: сеть, таймаут, лимит запросов, авторизация."""


class LLMClient(Protocol):
    async def complete(
        self, messages: Sequence[ChatMessage], *, max_tokens: int | None = None
    ) -> str: ...

    async def complete_json(
        self, messages: Sequence[ChatMessage], *, schema: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...
