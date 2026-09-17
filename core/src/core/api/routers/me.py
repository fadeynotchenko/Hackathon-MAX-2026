from __future__ import annotations

from fastapi import APIRouter

from core.api.dependencies import CurrentUserDep
from core.api.schemas.common import ErrorResponse
from core.api.schemas.user import UserProfileSchema

router = APIRouter(prefix="/me", tags=["me"])


@router.get(
    "",
    response_model=UserProfileSchema,
    responses={401: {"model": ErrorResponse}},
    operation_id="get_me",
    summary="Профиль текущего пользователя",
)
async def get_me(current: CurrentUserDep) -> UserProfileSchema:
    return UserProfileSchema.model_validate(current)
