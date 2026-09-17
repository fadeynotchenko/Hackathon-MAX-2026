"""Корреляция и access-лог каждого запроса.

Идентификатор берётся из ``X-Request-ID`` (его ставит nginx и пишет в свой
access-лог полем rid), иначе генерируется. Один и тот же id уходит клиенту
в заголовке ответа и в каждую запись лога через contextvars — по нему
строка nginx, строка API и жалоба пользователя сшиваются в одну историю.

Чистый ASGI, а не BaseHTTPMiddleware: без промежуточной задачи contextvars
доезжают до хендлера напрямую, а тело ответа не буферизуется.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.logs import bind_context, clear_context, log_event

logger = logging.getLogger("api.access")

REQUEST_ID_HEADER = "x-request-id"
_REQUEST_ID_MAX_LEN = 64
# Пинги liveness не должны засорять журнал.
_QUIET_PATHS = frozenset({"/api/v1/health"})


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == REQUEST_ID_HEADER.encode():
            raw = value.decode("latin-1")
            # Значение уходит в лог: пробелы и управляющие символы выкидываем целиком,
            # иначе чужой перевод строки подделает соседнюю запись.
            cleaned = "".join(ch for ch in raw.strip() if ch.isprintable() and not ch.isspace())
            return cleaned[:_REQUEST_ID_MAX_LEN] or None
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        bind_context(request_id=request_id, user_id=None)

        started = time.perf_counter()
        status: dict[str, Any] = {"code": None}

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            status["code"] = 500
            raise
        finally:
            path = scope.get("path", "")
            if path not in _QUIET_PATHS:
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                level = logging.WARNING if (status["code"] or 500) >= 500 else logging.INFO
                log_event(
                    logger,
                    level,
                    "http.request",
                    method=scope.get("method", ""),
                    path=path,
                    status=status["code"],
                    duration_ms=duration_ms,
                    client_ip=(scope.get("client") or ("", 0))[0],
                )
            clear_context()
