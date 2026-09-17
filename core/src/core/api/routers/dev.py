"""Dev-вход: initData тестового пользователя для мини-аппа в обычном браузере.

Роутер подключается только вне production (см. ``create_app``): в проде этого
пути нет вовсе. Подписывает тем же MAX_BOT_TOKEN, что проверяет ``/auth/max``,
поэтому вход проходит через настоящий код авторизации, без заглушек.

По умолчанию тестовый пользователь — первый из ADMIN_MAX_IDS (если список
задан), чтобы на локали был виден и админский раздел.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from core.api.dependencies import StateDep
from core.domain.initdata import build_dev_init_data

router = APIRouter(prefix="/dev", tags=["dev"])


class DevInitDataResponse(BaseModel):
    init_data: str = Field(description="Строка для POST /auth/max, подписана MAX_BOT_TOKEN")
    max_user_id: int
    is_admin: bool


@router.get(
    "/init-data",
    response_model=DevInitDataResponse,
    operation_id="dev_init_data",
    summary="initData тестового пользователя (только вне production)",
)
async def dev_init_data(
    state: StateDep,
    user_id: int | None = Query(default=None, gt=0),
    first_name: str = Query(default="Dev", max_length=64),
    username: str = Query(default="dev", max_length=64),
) -> DevInitDataResponse:
    admin_ids = sorted(state.app_config.admin_max_ids)
    max_user_id = user_id or (admin_ids[0] if admin_ids else 1)
    return DevInitDataResponse(
        init_data=build_dev_init_data(
            state.auth_config.bot_token,
            user_id=max_user_id,
            first_name=first_name,
            username=username or None,
        ),
        max_user_id=max_user_id,
        is_admin=max_user_id in admin_ids,
    )
