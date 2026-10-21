"""Подсказки реквизитов по реестрам для полей карточки и документа.

Только под Bearer: ключ DaData с дневным лимитом не должен работать на всех,
кто нашёл адрес API.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api.dependencies import CurrentUserDep, StateDep
from core.api.schemas.common import ErrorResponse
from core.api.schemas.documents import RequisiteSuggestionSchema
from core.usecases.documents import SuggestKind, suggest_requisites
from core.usecases.documents.lookup import MAX_QUERY_LENGTH

router = APIRouter(prefix="/suggest", tags=["documents"])


@router.get(
    "/{kind}",
    response_model=list[RequisiteSuggestionSchema],
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    operation_id="suggest_requisites",
    summary="Подсказки из реестров: организация по названию или ИНН, банк, адрес",
)
async def suggest(
    kind: SuggestKind,
    _current: CurrentUserDep,
    state: StateDep,
    query: str = Query(max_length=MAX_QUERY_LENGTH, description="Что набрал человек"),
) -> list[RequisiteSuggestionSchema]:
    items = await suggest_requisites(kind, query, client=state.suggest)
    return [RequisiteSuggestionSchema.model_validate(item) for item in items]
