"""Админские ручки: сводка, метрики по дням и отправка сообщения пользователю через бота."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, status

from core.api.dependencies import AdminDep, SessionDep, StateDep
from core.api.schemas.admin import (
    AdminMetricsResponse,
    AdminStatsResponse,
    NotifyRequest,
    NotifyResponse,
)
from core.api.schemas.common import ErrorResponse
from core.usecases.admin import admin_metrics
from core.usecases.admin.metrics import MAX_DAYS
from core.usecases.users import admin_stats

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}


@router.get(
    "/stats", response_model=AdminStatsResponse, responses=_ADMIN_ERRORS, operation_id="admin_stats"
)
async def admin_stats_route(_admin: AdminDep, session: SessionDep) -> AdminStatsResponse:
    stats = await admin_stats(session, now=datetime.now(UTC))
    return AdminStatsResponse.model_validate(stats)


@router.get(
    "/metrics",
    response_model=AdminMetricsResponse,
    responses=_ADMIN_ERRORS,
    operation_id="admin_metrics",
    summary="Метрики по дням: пользователи, документы, воронка, автозаполнение, доставки",
)
async def admin_metrics_route(
    _admin: AdminDep,
    session: SessionDep,
    days: int = Query(default=30, ge=1, le=MAX_DAYS, description="Сколько последних дней"),
) -> AdminMetricsResponse:
    metrics = await admin_metrics(session, days=days)
    return AdminMetricsResponse.model_validate(metrics)


@router.post(
    "/notify",
    response_model=NotifyResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ADMIN_ERRORS,
    operation_id="admin_notify",
    summary="Отправить сообщение пользователю в MAX (через бота)",
)
async def admin_notify(body: NotifyRequest, _admin: AdminDep, state: StateDep) -> NotifyResponse:
    # 202, а не 200: API только ставит событие в стрим, доставляет бот.
    event_id = await state.event_bus.notify_user(body.max_user_id, body.text, fmt=body.format)
    return NotifyResponse(event_id=event_id)
