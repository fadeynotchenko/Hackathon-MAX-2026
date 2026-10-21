"""Серверный таймаут на запрос.

Если хендлер не уложился в N секунд (зависшая БД, внешний сервис) —
задача отменяется, соединение из пула возвращается, клиент получает 504.
Без этого один медленный запрос удерживает воркер и коннект минутами.

Ручки с файлом в теле (``upload_paths``) живут дольше: модель читает фото или
голосовое заметно медленнее текста, и общий срок обрывал бы их на полпути.
"""

from __future__ import annotations

import asyncio
import logging
import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.logs import biz_error

logger = logging.getLogger(__name__)


class TimeoutMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        timeout_seconds: float,
        upload_paths: re.Pattern[str] | None = None,
        upload_timeout_seconds: float | None = None,
    ) -> None:
        self.app = app
        self.timeout_seconds = timeout_seconds
        self.upload_paths = upload_paths
        self.upload_timeout_seconds = upload_timeout_seconds or timeout_seconds

    def _timeout_for(self, path: str) -> float:
        if self.upload_paths is not None and self.upload_paths.match(path):
            return self.upload_timeout_seconds
        return self.timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False
        timeout_seconds = self._timeout_for(scope.get("path", ""))

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await asyncio.wait_for(self.app(scope, receive, tracking_send), timeout=timeout_seconds)
        except TimeoutError:
            biz_error(
                logger,
                "http.request.timeout",
                method=scope.get("method"),
                path=scope.get("path"),
                timeout_s=timeout_seconds,
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
