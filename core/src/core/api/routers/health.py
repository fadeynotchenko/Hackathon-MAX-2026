"""Liveness/readiness. Публичный и без авторизации — внутренностей не раскрывает."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.api.schemas.common import HealthResponse
from core.db import ping_db, ping_redis
from core.logs import biz_warn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
    operation_id="health",
)
async def health(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    for name, ping in (("database", ping_db), ("redis", ping_redis)):
        try:
            await ping()
            checks[name] = "ok"
        except Exception as exc:
            biz_warn(logger, "health.check_failed", component=name, error=str(exc))
            checks[name] = "error"
    # Фоновый потребитель событий запускается lifespan'ом; в тестах его нет.
    task = getattr(request.app.state, "events_task", None)
    if task is not None:
        checks["events_worker"] = "error" if task.done() else "ok"
    degraded = any(value != "ok" for value in checks.values())
    body = HealthResponse(status="degraded" if degraded else "ok", checks=checks)
    return JSONResponse(status_code=503 if degraded else 200, content=body.model_dump())
