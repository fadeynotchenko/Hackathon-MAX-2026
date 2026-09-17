"""Серверный таймаут на запрос.

Если хендлер не уложился в N секунд (зависшая БД, внешний сервис) —
задача отменяется, соединение из пула возвращается, клиент получает 504.
Без этого один медленный запрос удерживает воркер и коннект минутами.
"""

from __future__ import annotations

import asyncio
import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.logs import biz_error

logger = logging.getLogger(__name__)


class TimeoutMiddleware:
    def __init__(self, app: ASGIApp, *, timeout_seconds: float) -> None:
        self.app = app
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await asyncio.wait_for(
                self.app(scope, receive, tracking_send), timeout=self.timeout_seconds
            )
        except TimeoutError:
            biz_error(
                logger,
                "http.request.timeout",
                method=scope.get("method"),
                path=scope.get("path"),
                timeout_s=self.timeout_seconds,
            )
            # Ответ уже начался — отправить 504 нельзя, соединение просто оборвётся.
            if not response_started:
                response = JSONResponse(
                    status_code=504,
                    content={
                        "detail": "Превышено время ожидания",
                        "code": "http.timeout",
                        "request_id": scope.get("state", {}).get("request_id"),
                    },
                )
                await response(scope, receive, send)
