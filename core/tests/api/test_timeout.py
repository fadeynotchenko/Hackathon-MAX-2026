"""Срок запроса: общий для всех ручек и долгий для ручек с файлом."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send

from core.api.middlewares import TimeoutMiddleware
from core.api.uploads import UPLOAD_PATHS


async def _slow(scope: Scope, receive: Receive, send: Send) -> None:
    await asyncio.sleep(0.2)
    await PlainTextResponse("готово")(scope, receive, send)


@pytest.fixture
async def slow_client() -> AsyncIterator[AsyncClient]:
    app = TimeoutMiddleware(
        _slow, timeout_seconds=0.05, upload_paths=UPLOAD_PATHS, upload_timeout_seconds=5
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_ordinary_request_is_cut_off(slow_client: AsyncClient) -> None:
    response = await slow_client.post("/api/v1/documents/7/agent/fill")
    assert response.status_code == 504
    assert response.json()["code"] == "http.timeout"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/documents/7/agent/recognize",
        "/api/v1/documents/7/agent/voice",
        "/api/v1/requisites/recognize",
        "/api/v1/templates/import",
        "/api/v1/documents/import",
    ],
)
async def test_upload_waits_for_the_model(slow_client: AsyncClient, path: str) -> None:
    response = await slow_client.post(path)
    assert response.status_code == 200 and response.text == "готово"


def test_upload_paths_are_exactly_the_routes_with_a_file(app: FastAPI) -> None:
    """Новая ручка с файлом без долгого срока снова упиралась бы в общий таймаут."""
    paths = {
        path.replace("{document_id}", "1")
        .replace("{organization_id}", "1")
        .replace("{kind}", "signature"): operations
        for path, operations in app.openapi()["paths"].items()
    }
    with_file = {
        path
        for path, operations in paths.items()
        for operation in operations.values()
        if any(
            media.get("schema", {}).get("format") == "binary"
            for media in operation.get("requestBody", {}).get("content", {}).values()
        )
    }
    matched = {path for path in paths if UPLOAD_PATHS.match(path)}
    assert with_file and matched == with_file
