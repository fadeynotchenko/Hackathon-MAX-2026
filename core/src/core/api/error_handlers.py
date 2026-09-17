"""Единый формат ошибок API: ``{"detail": str, "code": str, "request_id": str}``.

``detail`` — текст, который мини-апп показывает как есть; ``code`` — машинный
код для ветвления на клиенте и поиска в логах. Внутренности исключений
наружу не уходят никогда: их место в логе под тем же request_id.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.domain.exceptions import AppError
from core.logs import biz_error, biz_warn

logger = logging.getLogger("api")


def request_id_of(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_response(
    request: Request, status: int, detail: object, code: str, headers: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"detail": detail, "code": code, "request_id": request_id_of(request)},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        biz_warn(
            logger,
            "api.error.app",
            code=exc.code,
            status=exc.status_code,
            path=request.url.path,
            detail=exc.log_message or exc.public_message,
        )
        return _error_response(request, exc.status_code, exc.public_message, exc.code)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(
            request, exc.status_code, exc.detail, "http.error", getattr(exc, "headers", None)
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # detail — всегда строка (клиент показывает её как есть), подробности — отдельно.
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Некорректные данные запроса",
                "code": "validation",
                "request_id": request_id_of(request),
                "errors": jsonable_encoder(exc.errors()),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        biz_error(
            logger,
            "api.error.unhandled",
            error_type=type(exc).__name__,
            path=request.url.path,
            method=request.method,
            exc_info=exc,
        )
        return _error_response(request, 500, "Внутренняя ошибка сервера", "internal")
