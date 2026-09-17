"""Админские ручки: сводка и отправка сообщения пользователю через бота."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status

from core.api.dependencies import AdminDep, SessionDep, StateDep
from core.api.schemas.admin import AdminStatsResponse, NotifyRequest, NotifyResponse
from core.api.schemas.common import ErrorResponse
from core.usecases.users import admin_stats

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}}


@router.get(
    "/stats", response_model=AdminStatsResponse, responses=_ADMIN_ERRORS, operation_id="admin_stats"
)
async def admin_stats_route(_admin: AdminDep, session: SessionDep) -> AdminStatsResponse:
    stats = await admin_stats(session, now=datetime.now(UTC))
    return AdminStatsResponse.model_validate(stats)


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
