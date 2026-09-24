"""Ручки помощника: заполнить поля из сообщения, ответить по документу, написать письмо."""

from __future__ import annotations

from fastapi import APIRouter

from core.api.dependencies import CurrentUserDep, SessionDep, StateDep
from core.api.schemas.common import ErrorResponse
from core.api.schemas.documents import (
    AgentAskRequest,
    AgentFillRequest,
    AgentFillResponse,
    AgentTextResponse,
    DocumentSchema,
    FieldErrorSchema,
)
from core.usecases.agent import answer_question, draft_cover_letter, fill_from_message

router = APIRouter(prefix="/documents/{document_id}/agent", tags=["agent"])
_ERRORS = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@router.post(
    "/fill",
    response_model=AgentFillResponse,
    responses=_ERRORS,
    operation_id="agent_fill",
    summary="Заполнить поля документа из сообщения",
)
async def fill(
    document_id: int,
    payload: AgentFillRequest,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
) -> AgentFillResponse:
    result = await fill_from_message(
        session,
        user_id=current.id,
        document_id=document_id,
        message=payload.message,
        llm=state.llm,
    )
    return AgentFillResponse(
        reply=result.reply,
        filled=list(result.filled),
        rejected=[FieldErrorSchema.model_validate(e) for e in result.rejected],
        document=DocumentSchema.model_validate(result.document),
    )


@router.post(
    "/ask",
    response_model=AgentTextResponse,
    responses=_ERRORS,
    operation_id="agent_ask",
    summary="Ответить на вопрос по документу",
)
async def ask(
    document_id: int,
    payload: AgentAskRequest,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
) -> AgentTextResponse:
    answer = await answer_question(
        session,
        user_id=current.id,
        document_id=document_id,
        question=payload.question,
        llm=state.llm,
    )
    return AgentTextResponse(text=answer)


@router.post(
    "/cover-letter",
    response_model=AgentTextResponse,
    responses=_ERRORS,
    operation_id="agent_cover_letter",
    summary="Черновик сопроводительного сообщения контрагенту",
)
async def cover_letter(
    document_id: int, current: CurrentUserDep, session: SessionDep, state: StateDep
) -> AgentTextResponse:
    text = await draft_cover_letter(
        session, user_id=current.id, document_id=document_id, llm=state.llm
    )
    return AgentTextResponse(text=text)
