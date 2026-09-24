"""Скачивание вложения из хранилища MAX: лимит размера, ошибки хранилища, только https."""

from __future__ import annotations

import httpx
import pytest

from core.files import InboundFileError, InboundFileTooLargeError, fetch_media

URL = "https://i.max.test/photo?id=1"


def _transport(status: int = 200, body: bytes = b"\xff\xd8\xff", headers: dict | None = None):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=body, headers=headers)

    return httpx.MockTransport(handler), seen


async def test_downloads_the_file_and_asks_for_plain_formats() -> None:
    transport, seen = _transport(body=b"\xff\xd8\xff" + b"1" * 10)
    data = await fetch_media(URL, max_bytes=100, timeout_seconds=5, transport=transport)
    assert data == b"\xff\xd8\xff" + b"1" * 10
    assert seen[0].headers["Accept"].startswith("image/jpeg")


async def test_declared_size_over_the_limit_stops_early() -> None:
    transport, _ = _transport(body=b"1" * 10, headers={"Content-Length": "5000"})
    with pytest.raises(InboundFileTooLargeError):
        await fetch_media(URL, max_bytes=100, timeout_seconds=5, transport=transport)


async def test_body_over_the_limit_is_cut_while_streaming() -> None:
    transport, _ = _transport(body=b"1" * 500)
    with pytest.raises(InboundFileTooLargeError):
        await fetch_media(URL, max_bytes=100, timeout_seconds=5, transport=transport)


@pytest.mark.parametrize("status", [403, 404, 500])
async def test_storage_errors_are_reported(status: int) -> None:
    transport, _ = _transport(status=status)
    with pytest.raises(InboundFileError):
        await fetch_media(URL, max_bytes=100, timeout_seconds=5, transport=transport)


async def test_network_failure_is_an_inbound_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(InboundFileError):
        await fetch_media(
            URL, max_bytes=100, timeout_seconds=5, transport=httpx.MockTransport(handler)
        )


async def test_only_https_links_are_followed() -> None:
    transport, seen = _transport()
    with pytest.raises(InboundFileError):
        await fetch_media(
            "http://10.0.0.1/admin", max_bytes=100, timeout_seconds=5, transport=transport
        )
    assert seen == []
