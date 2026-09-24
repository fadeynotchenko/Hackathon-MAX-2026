from __future__ import annotations

from fastapi import APIRouter, status

from core.api.dependencies import CurrentUserDep, SessionDep
from core.api.schemas.common import ErrorResponse, IdPath, OkResponse
from core.api.schemas.documents import (
    CounterpartyRequest,
    CounterpartySchema,
)
from core.usecases.documents import (
    create_counterparty,
    delete_counterparty,
    list_counterparties,
    update_counterparty,
)

router = APIRouter(tags=["documents"])
_ERRORS = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.get(
    "/counterparties",
    response_model=list[CounterpartySchema],
    responses={401: {"model": ErrorResponse}},
    operation_id="list_counterparties",
    summary="Карточки контрагентов",
)
async def get_all(current: CurrentUserDep, session: SessionDep) -> list[CounterpartySchema]:
    items = await list_counterparties(session, user_id=current.id)
    return [CounterpartySchema.model_validate(item) for item in items]


@router.post(
    "/counterparties",
    response_model=CounterpartySchema,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    operation_id="create_counterparty",
    summary="Завести контрагента",
)
async def create(
    payload: CounterpartyRequest, current: CurrentUserDep, session: SessionDep
) -> CounterpartySchema:
    created = await create_counterparty(
        session, user_id=current.id, name=payload.name, values=payload.values
    )
    return CounterpartySchema.model_validate(created)


@router.put(
    "/counterparties/{counterparty_id}",
    response_model=CounterpartySchema,
    responses=_ERRORS,
    operation_id="update_counterparty",
    summary="Изменить карточку контрагента",
)
async def update(
    counterparty_id: IdPath,
    payload: CounterpartyRequest,
    current: CurrentUserDep,
    session: SessionDep,
) -> CounterpartySchema:
    updated = await update_counterparty(
        session,
        user_id=current.id,
        counterparty_id=counterparty_id,
        name=payload.name,
        values=payload.values,
    )
    return CounterpartySchema.model_validate(updated)


@router.delete(
    "/counterparties/{counterparty_id}",
    response_model=OkResponse,
    responses=_ERRORS,
    operation_id="delete_counterparty",
    summary="Удалить карточку контрагента",
)
async def delete(
    counterparty_id: IdPath, current: CurrentUserDep, session: SessionDep
) -> OkResponse:
    await delete_counterparty(session, user_id=current.id, counterparty_id=counterparty_id)
    return OkResponse()
