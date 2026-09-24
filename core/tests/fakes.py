"""Подставные внешние сервисы для тестов: модель с заранее заданными ответами.

Модель помнит, что у неё спрашивали, — тесты проверяют и ответ сценария, и то,
какой контекст ушёл провайдеру.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.llm.client import ChatMessage, LLMError, LLMUnavailableError


class FakeLLM:
    def __init__(
        self,
        *,
        text: str = "",
        json_reply: Mapping[str, Any] | None = None,
        json_replies: list[Mapping[str, Any]] | None = None,
        unavailable: bool = False,
        error: LLMError | None = None,
    ) -> None:
        self.text = text
        self.json_reply = dict(json_reply or {})
        self.json_replies = [dict(r) for r in json_replies or []]
        self.error = error or (LLMUnavailableError("fake: недоступна") if unavailable else None)
        self.calls: list[tuple[str, list[ChatMessage], Mapping[str, Any] | None]] = []

    async def complete(
        self, messages: Sequence[ChatMessage], *, max_tokens: int | None = None
    ) -> str:
        self.calls.append(("text", list(messages), None))
        if self.error is not None:
            raise self.error
        return self.text

    async def complete_json(
        self, messages: Sequence[ChatMessage], *, schema: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(("json", list(messages), schema))
        if self.error is not None:
            raise self.error
        if self.json_replies:
            return self.json_replies.pop(0)
        return dict(self.json_reply)

    async def aclose(self) -> None:
        return None
