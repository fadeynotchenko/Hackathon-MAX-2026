"""Свои организации: реквизиты, основная, подпись и печать картинками."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response, status

from core.api.dependencies import CurrentUserDep, SessionDep
from core.api.schemas.common import ErrorResponse, IdPath, OkResponse
from core.api.schemas.documents import OrganizationRequest, OrganizationSchema
from core.api.uploads import binary_body, read_body
from core.usecases.documents import (
    create_organization,
    delete_organization,
    delete_organization_mark,
    list_organizations,
    organization_mark,
    set_organization_mark,
    update_organization,
)
from core.usecases.documents.organizations import MARK_MAX_BYTES

MarkKind = Literal["signature", "stamp"]

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
    organization_id: IdPath,
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
async def delete(
    organization_id: IdPath, current: CurrentUserDep, session: SessionDep
) -> OkResponse:
    await delete_organization(session, user_id=current.id, organization_id=organization_id)
    return OkResponse()


_MARK_ERRORS = _ERRORS | {413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}}


@router.put(
    "/organizations/{organization_id}/marks/{kind}",
    response_model=OrganizationSchema,
    responses=_MARK_ERRORS,
    operation_id="set_organization_mark",
    summary="Подпись (signature) или печать (stamp) картинкой: встанет в документы организации",
    openapi_extra=binary_body(
        "image/jpeg", "image/png", "image/webp", description="Фото на белом листе: JPG, PNG, WEBP"
    ),
)
async def put_mark(
    organization_id: IdPath,
    kind: MarkKind,
    request: Request,
    current: CurrentUserDep,
    session: SessionDep,
) -> OrganizationSchema:
    updated = await set_organization_mark(
        session,
        user_id=current.id,
        organization_id=organization_id,
        kind=kind,
        data=await read_body(request, max_bytes=MARK_MAX_BYTES),
    )
    return OrganizationSchema.model_validate(updated)


@router.get(
    "/organizations/{organization_id}/marks/{kind}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}, **_ERRORS},
    operation_id="get_organization_mark",
    summary="Загруженная подпись или печать — PNG с прозрачным фоном",
)
async def get_mark(
    organization_id: IdPath, kind: MarkKind, current: CurrentUserDep, session: SessionDep
) -> Response:
    data = await organization_mark(
        session, user_id=current.id, organization_id=organization_id, kind=kind
    )
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.delete(
    "/organizations/{organization_id}/marks/{kind}",
    response_model=OrganizationSchema,
    responses=_ERRORS,
    operation_id="delete_organization_mark",
    summary="Убрать подпись или печать из документов организации",
)
async def delete_mark(
    organization_id: IdPath, kind: MarkKind, current: CurrentUserDep, session: SessionDep
) -> OrganizationSchema:
    updated = await delete_organization_mark(
        session, user_id=current.id, organization_id=organization_id, kind=kind
    )
    return OrganizationSchema.model_validate(updated)
