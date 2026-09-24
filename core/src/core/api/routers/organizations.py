from __future__ import annotations

from fastapi import APIRouter, status

from core.api.dependencies import CurrentUserDep, SessionDep
from core.api.schemas.common import ErrorResponse, OkResponse
from core.api.schemas.documents import OrganizationRequest, OrganizationSchema
from core.usecases.documents import (
    create_organization,
    delete_organization,
    list_organizations,
    update_organization,
)

router = APIRouter(tags=["documents"])
_ERRORS = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.get(
    "/organizations",
    response_model=list[OrganizationSchema],
    responses={401: {"model": ErrorResponse}},
    operation_id="list_organizations",
    summary="Мои организации: основная первой",
)
async def get_all(current: CurrentUserDep, session: SessionDep) -> list[OrganizationSchema]:
    items = await list_organizations(session, user_id=current.id)
    return [OrganizationSchema.model_validate(item) for item in items]


@router.post(
    "/organizations",
    response_model=OrganizationSchema,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    operation_id="create_organization",
    summary="Завести свою организацию; первая становится основной",
)
async def create(
    payload: OrganizationRequest, current: CurrentUserDep, session: SessionDep
) -> OrganizationSchema:
    created = await create_organization(
        session,
        user_id=current.id,
        name=payload.name,
        values=payload.values,
        is_default=payload.is_default,
    )
    return OrganizationSchema.model_validate(created)


@router.put(
    "/organizations/{organization_id}",
    response_model=OrganizationSchema,
    responses=_ERRORS,
    operation_id="update_organization",
    summary="Изменить организацию или сделать её основной",
)
async def update(
    organization_id: int,
    payload: OrganizationRequest,
    current: CurrentUserDep,
    session: SessionDep,
) -> OrganizationSchema:
    updated = await update_organization(
        session,
        user_id=current.id,
        organization_id=organization_id,
        name=payload.name,
        values=payload.values,
        is_default=payload.is_default,
    )
    return OrganizationSchema.model_validate(updated)


@router.delete(
    "/organizations/{organization_id}",
    response_model=OkResponse,
    responses=_ERRORS,
    operation_id="delete_organization",
    summary="Удалить организацию; основной станет следующая",
)
async def delete(organization_id: int, current: CurrentUserDep, session: SessionDep) -> OkResponse:
    await delete_organization(session, user_id=current.id, organization_id=organization_id)
    return OkResponse()
