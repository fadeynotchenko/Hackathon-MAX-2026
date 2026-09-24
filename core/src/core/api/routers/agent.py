"""Ручки помощника: заполнить поля из сообщения, фото, скана или голосового,
ответить по документу, написать письмо; распознать реквизиты для карточки.

Файл приходит сырым телом запроса (``Content-Type`` — тип файла): мини-апп
отправляет снимок или запись как есть, без multipart-обёртки.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from core.api.dependencies import CurrentUserDep, SessionDep, StateDep
from core.api.schemas.common import ErrorResponse
from core.api.schemas.documents import (
    AgentAskRequest,
    AgentFillRequest,
    AgentFillResponse,
    AgentTextResponse,
    DocumentSchema,
    FieldErrorSchema,
    RecognizedRequisitesSchema,
    VoiceFillResponse,
)
from core.api.uploads import AUDIO_TYPES, DOCUMENT_TYPES, IMAGE_TYPES, binary_body, read_body
from core.usecases.agent import (
    AgentFillResult,
    answer_question,
    draft_cover_letter,
    fill_from_file,
    fill_from_message,
    fill_from_voice,
    recognize_requisites,
)

router = APIRouter(prefix="/documents/{document_id}/agent", tags=["agent"])
requisites_router = APIRouter(prefix="/requisites", tags=["agent"])
_ERRORS = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}
_UPLOAD_ERRORS = _ERRORS | {
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
_HINT = Query(
    default="",
    max_length=500,
    description="Слова пользователя к файлу, например «это реквизиты покупателя»",
)


def _fill_response(result: AgentFillResult) -> AgentFillResponse:
    return AgentFillResponse(
        reply=result.reply,
        filled=list(result.filled),
        rejected=[FieldErrorSchema.model_validate(e) for e in result.rejected],
        document=DocumentSchema.model_validate(result.document),
    )


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
    return _fill_response(result)


@router.post(
    "/recognize",
    response_model=AgentFillResponse,
    responses=_UPLOAD_ERRORS,
    operation_id="agent_recognize",
    summary="Заполнить поля документа с фото или скана",
    openapi_extra=binary_body(
        *IMAGE_TYPES, *DOCUMENT_TYPES, description="Фото (JPG, PNG) или скан (PDF, DOCX)"
    ),
)
async def recognize(
    document_id: int,
    request: Request,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
    hint: str = _HINT,
) -> AgentFillResponse:
    limit = state.files_config.media_max_bytes
    result = await fill_from_file(
        session,
        user_id=current.id,
        document_id=document_id,
        data=await read_body(request, max_bytes=limit),
        llm=state.llm,
        max_bytes=limit,
        request=hint,
    )
    return _fill_response(result)


@router.post(
    "/voice",
    response_model=VoiceFillResponse,
    responses=_UPLOAD_ERRORS,
    operation_id="agent_voice",
    summary="Заполнить поля документа голосовым",
    openapi_extra=binary_body(*AUDIO_TYPES, description="Голосовое: OGG, MP3, M4A, WEBM, WAV"),
)
async def voice(
    document_id: int,
    request: Request,
    current: CurrentUserDep,
    session: SessionDep,
    state: StateDep,
) -> VoiceFillResponse:
    limit = state.files_config.media_max_bytes
    result = await fill_from_voice(
        session,
        user_id=current.id,
        document_id=document_id,
        data=await read_body(request, max_bytes=limit),
        llm=state.llm,
        max_bytes=limit,
    )
    return VoiceFillResponse(
        transcript=result.transcript, **_fill_response(result.fill).model_dump()
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


@requisites_router.post(
    "/recognize",
    response_model=RecognizedRequisitesSchema,
    responses={k: v for k, v in _UPLOAD_ERRORS.items() if k != 404},
    operation_id="recognize_requisites",
    summary="Реквизиты организации с фото для карточки контрагента или своей компании",
    openapi_extra=binary_body(
        *IMAGE_TYPES, *DOCUMENT_TYPES, description="Фото или скан карточки предприятия, счёта"
    ),
)
async def recognize_card(
    request: Request,
    _current: CurrentUserDep,
    state: StateDep,
    hint: str = _HINT,
) -> RecognizedRequisitesSchema:
    limit = state.files_config.media_max_bytes
    result = await recognize_requisites(
        data=await read_body(request, max_bytes=limit),
        llm=state.llm,
        max_bytes=limit,
        request=hint,
    )
    return RecognizedRequisitesSchema.model_validate(result)
