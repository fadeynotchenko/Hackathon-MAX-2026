"""Адаптер GigaChat на подменённом транспорте: OAuth, кеш токена, повтор на 401."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from core.llm import ChatMessage, GigaChatClient, GigaChatConfig, LLMError, LLMUnavailableError

CFG = GigaChatConfig(
    auth_key="dGVzdDp0ZXN0",
    scope="GIGACHAT_API_PERS",
    model="GigaChat-2-Max",
    api_url="https://api.giga.chat/v1",
    auth_url="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
    ca_bundle=Path("certs/russian_trusted_root_ca.pem"),
    timeout_seconds=5,
)
MESSAGES = [ChatMessage("user", "Привет")]


class FakeGigaChat:
    """Минимальная копия двух ручек GigaChat, которые использует адаптер."""

    def __init__(self, *, chat_statuses: list[int] | None = None, content: str = "Ответ") -> None:
        self.chat_statuses = list(chat_statuses or [])
        self.content = content
        self.token_calls: list[httpx.Request] = []
        self.chat_calls: list[httpx.Request] = []
        self.issued = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/oauth":
            self.token_calls.append(request)
            self.issued += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"token-{self.issued}",
                    "expires_at": (time.time() + 1800) * 1000,
                },
            )
        self.chat_calls.append(request)
        status = self.chat_statuses.pop(0) if self.chat_statuses else 200
        if status != 200:
            return httpx.Response(status, json={"message": "nope"})
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": self.content}}]}
        )

    def client(self) -> GigaChatClient:
        return GigaChatClient(CFG, transport=httpx.MockTransport(self.handler))


async def test_token_is_requested_once_and_reused() -> None:
    api = FakeGigaChat()
    client = api.client()
    assert await client.complete(MESSAGES) == "Ответ"
    assert await client.complete(MESSAGES) == "Ответ"

    assert len(api.token_calls) == 1, "токен живёт 30 минут, второй раз его не просим"
    oauth = api.token_calls[0]
    assert oauth.headers["Authorization"] == "Basic dGVzdDp0ZXN0"
    assert len(oauth.headers["RqUID"]) == 36
    assert oauth.content == b"scope=GIGACHAT_API_PERS"
    assert api.chat_calls[1].headers["Authorization"] == "Bearer token-1"


async def test_expired_token_is_refreshed_once_on_401() -> None:
    api = FakeGigaChat(chat_statuses=[401, 200])
    client = api.client()
    assert await client.complete(MESSAGES) == "Ответ"
    assert len(api.token_calls) == 2
    assert api.chat_calls[-1].headers["Authorization"] == "Bearer token-2"


async def test_second_401_means_the_key_is_rejected() -> None:
    api = FakeGigaChat(chat_statuses=[401, 401])
    with pytest.raises(LLMUnavailableError):
        await api.client().complete(MESSAGES)


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_overload_is_temporary(status: int) -> None:
    api = FakeGigaChat(chat_statuses=[status])
    with pytest.raises(LLMUnavailableError):
        await api.client().complete(MESSAGES)


async def test_json_mode_sends_strict_schema_and_parses_answer() -> None:
    api = FakeGigaChat(content='{"total": "120 000", "client_name": "ООО «Ромашка»"}')
    schema = {"type": "object", "properties": {"total": {"type": "string"}}}

    data = await api.client().complete_json(MESSAGES, schema=schema)

    assert data == {"total": "120 000", "client_name": "ООО «Ромашка»"}
    payload = json.loads(api.chat_calls[0].content)
    assert payload["model"] == "GigaChat-2-Max"
    assert payload["response_format"] == {"type": "json_schema", "schema": schema, "strict": True}
    assert payload["temperature"] == 0.0


async def test_non_json_answer_is_a_bad_response() -> None:
    api = FakeGigaChat(content="Конечно, вот поля: сумма 120 000")
    with pytest.raises(LLMError) as exc:
        await api.client().complete_json(MESSAGES, schema={"type": "object"})
    assert not isinstance(exc.value, LLMUnavailableError)
