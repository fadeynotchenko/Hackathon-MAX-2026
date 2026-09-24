"""Адаптер GigaChat на подменённом транспорте: OAuth, кеш токена, повтор на 401, вложения."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest

from core.llm import (
    Attachment,
    ChatMessage,
    GigaChatClient,
    GigaChatConfig,
    LLMError,
    LLMInputError,
    LLMUnavailableError,
    gigachat,
)

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
    """Минимальная копия ручек GigaChat, которые использует адаптер."""

    def __init__(
        self,
        *,
        chat_statuses: list[int] | None = None,
        content: str = "Ответ",
        arguments: object = None,
        upload_status: int = 200,
        delete_status: int = 200,
    ) -> None:
        self.chat_statuses = list(chat_statuses or [])
        self.content = content
        self.arguments = arguments
        self.upload_status = upload_status
        self.delete_status = delete_status
        self.token_calls: list[httpx.Request] = []
        self.chat_calls: list[httpx.Request] = []
        self.uploads: list[httpx.Request] = []
        self.deleted: list[str] = []
        self.issued = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/files":
            self.uploads.append(request)
            if self.upload_status != 200:
                return httpx.Response(self.upload_status, json={"message": "unsupported"})
            return httpx.Response(200, json={"id": f"file-{len(self.uploads)}", "object": "file"})
        if request.url.path.endswith("/delete"):
            self.deleted.append(request.url.path.split("/")[-2])
            return httpx.Response(self.delete_status, json={"deleted": True})
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
        message: dict[str, object] = {"role": "assistant", "content": self.content}
        if self.arguments is not None:
            message = {
                "role": "assistant",
                "content": "",
                "function_call": {"name": "submit_answer", "arguments": self.arguments},
            }
        return httpx.Response(200, json={"choices": [{"message": message}]})

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


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gigachat, "RATE_LIMIT_BACKOFF_SECONDS", 0)


@pytest.mark.parametrize("status", [500, 503])
async def test_overload_is_temporary(status: int) -> None:
    api = FakeGigaChat(chat_statuses=[status])
    with pytest.raises(LLMUnavailableError):
        await api.client().complete(MESSAGES)


async def test_rate_limit_is_waited_out() -> None:
    api = FakeGigaChat(chat_statuses=[429, 429])
    assert await api.client().complete(MESSAGES) == "Ответ"
    assert len(api.chat_calls) == 3


async def test_rate_limit_that_does_not_pass_is_temporary() -> None:
    api = FakeGigaChat(chat_statuses=[429] * (gigachat.RATE_LIMIT_RETRIES + 1))
    with pytest.raises(LLMUnavailableError):
        await api.client().complete(MESSAGES)


async def test_requests_queue_up_to_the_plan_limit() -> None:
    in_flight = peak = 0

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        if request.url.path == "/api/v2/oauth":
            return httpx.Response(200, json={"access_token": "t", "expires_at": 9e15})
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "Ответ"}}]})

    client = GigaChatClient(CFG, transport=httpx.MockTransport(slow))
    answers = await asyncio.gather(*(client.complete(MESSAGES) for _ in range(3)))
    assert answers == ["Ответ"] * 3
    assert peak == 1, "на тарифе физлиц второй параллельный запрос получил бы 429"


async def test_json_mode_forces_a_function_call_and_returns_its_arguments() -> None:
    api = FakeGigaChat(arguments={"total": "120 000", "client_name": "ООО «Ромашка»"})
    schema = {"type": "object", "properties": {"total": {"type": "string"}}}

    data = await api.client().complete_json(MESSAGES, schema=schema)

    assert data == {"total": "120 000", "client_name": "ООО «Ромашка»"}
    payload = json.loads(api.chat_calls[0].content)
    assert payload["model"] == "GigaChat-2-Max"
    assert "response_format" not in payload, "строгая схема ломает JSON у GigaChat"
    (function,) = payload["functions"]
    assert function["name"] == "submit_answer" and function["parameters"] == schema
    assert payload["function_call"] == {"name": "submit_answer"}
    assert payload["temperature"] == 0.0


@pytest.mark.parametrize("arguments", [None, "не объект"])
async def test_answer_without_function_arguments_is_a_bad_response(arguments: object) -> None:
    api = FakeGigaChat(content="Конечно, вот поля: сумма 120 000", arguments=arguments)
    with pytest.raises(LLMError) as exc:
        await api.client().complete_json(MESSAGES, schema={"type": "object"})
    assert not isinstance(exc.value, LLMUnavailableError)


PHOTO = Attachment(b"\xff\xd8\xff\xe0 jpeg", "image/jpeg", "photo.jpg")


async def test_attachment_is_uploaded_referenced_and_deleted() -> None:
    api = FakeGigaChat(arguments={"inn": "7707083893"})
    messages = [ChatMessage("system", "Правила"), ChatMessage("user", "Фото", (PHOTO,))]

    data = await api.client().complete_json(messages, schema={"type": "object"})

    assert data == {"inn": "7707083893"}
    (upload,) = api.uploads
    assert upload.headers["Authorization"] == "Bearer token-1"
    body = upload.content
    assert b'name="purpose"' in body and b"general" in body
    assert b'filename="photo.jpg"' in body and b"Content-Type: image/jpeg" in body
    payload = json.loads(api.chat_calls[0].content)
    assert payload["messages"][0] == {"role": "system", "content": "Правила"}
    assert payload["messages"][1]["attachments"] == ["file-1"]
    assert api.deleted == ["file-1"], "файл у провайдера живёт один запрос"


async def test_uploaded_file_is_deleted_even_if_chat_fails() -> None:
    api = FakeGigaChat(chat_statuses=[503])
    with pytest.raises(LLMUnavailableError):
        await api.client().complete([ChatMessage("user", "Фото", (PHOTO,))])
    assert api.deleted == ["file-1"]


async def test_rejected_file_is_an_input_error() -> None:
    api = FakeGigaChat(upload_status=400)
    with pytest.raises(LLMInputError):
        await api.client().complete([ChatMessage("user", "Фото", (PHOTO,))])
    assert api.chat_calls == [] and api.deleted == []


async def test_failed_cleanup_does_not_break_the_answer() -> None:
    api = FakeGigaChat(delete_status=500)
    answer = await api.client().complete([ChatMessage("user", "Фото", (PHOTO,))])
    assert answer == "Ответ" and api.deleted == ["file-1"]


def test_attachment_bytes_stay_out_of_repr() -> None:
    scan = Attachment(b"passport 4510 123456", "image/png", "scan.png")
    assert "4510" not in repr(scan) and "scan.png" in repr(scan)
