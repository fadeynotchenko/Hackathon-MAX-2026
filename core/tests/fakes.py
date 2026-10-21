"""Подставные внешние сервисы для тестов: модель и реестр подсказок с заранее
заданными ответами.

Модель помнит, что у неё спрашивали, — тесты проверяют и ответ сценария, и то,
какой контекст ушёл провайдеру.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.llm.client import ChatMessage, LLMError, LLMUnavailableError
from core.suggest import AddressRecord, BankRecord, CompanyRecord, SuggestUnavailableError


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


class FakeSuggest:
    def __init__(
        self,
        *,
        companies: Sequence[CompanyRecord] = (),
        banks: Sequence[BankRecord] = (),
        addresses: Sequence[AddressRecord] = (),
        unavailable: bool = False,
    ) -> None:
        self._companies = list(companies)
        self._banks = list(banks)
        self._addresses = list(addresses)
        self.unavailable = unavailable
        self.queries: list[tuple[str, str]] = []

    def _answer[T](self, kind: str, query: str, records: list[T]) -> list[T]:
        self.queries.append((kind, query))
        if self.unavailable:
            raise SuggestUnavailableError("fake: недоступен")
        return records

    async def companies(self, query: str, *, count: int) -> list[CompanyRecord]:
        return self._answer("company", query, self._companies)[:count]

    async def banks(self, query: str, *, count: int) -> list[BankRecord]:
        return self._answer("bank", query, self._banks)[:count]

    async def addresses(self, query: str, *, count: int) -> list[AddressRecord]:
        return self._answer("address", query, self._addresses)[:count]

    async def aclose(self) -> None:
        return None
