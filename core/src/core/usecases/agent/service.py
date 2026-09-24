"""Сценарии агента: заполнить поля из сообщения, ответить по документу, написать письмо.

Каналонейтральны, как и остальные сценарии: их одинаково зовёт ручка мини-аппа и
обработчик сообщения бота. Всё, что предлагает модель, проходит через те же
``set_fields`` и доменную проверку, что и ручной ввод, и сохраняется с
источником ``agent`` без подтверждения — готовым документ станет, когда человек
скажет «всё верно».
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldError, FieldValue, ValueSource
from core.domain.exceptions import AppError
from core.llm import ChatMessage, LLMClient, LLMError, LLMUnavailableError
from core.usecases.agent.prompts import (
    ASK_INSTRUCTIONS,
    COVER_INSTRUCTIONS,
    FILL_INSTRUCTIONS,
    current_values,
    describe_document,
    describe_fields,
    fields_schema,
)
from core.usecases.documents import DocumentView, get_document, set_fields

MAX_ANSWER_TOKENS = 600


@dataclass(frozen=True)
class AgentFillResult:
    document: DocumentView
    filled: tuple[str, ...]
    rejected: tuple[FieldError, ...]
    reply: str


def _require(llm: LLMClient | None) -> LLMClient:
    if llm is None:
        raise AppError(
            "Помощник сейчас выключен, заполните поля вручную",
            code="agent.unavailable",
            status_code=503,
        )
    return llm


def _map_llm_error(exc: LLMError) -> AppError:
    if isinstance(exc, LLMUnavailableError):
        return AppError(
            "Помощник не отвечает, попробуйте позже или заполните поля вручную",
            code="agent.unavailable",
            status_code=503,
            log_message=str(exc),
        )
    return AppError(
        "Помощник ответил непонятно, попробуйте переформулировать",
        code="agent.bad_response",
        status_code=502,
        log_message=str(exc),
    )


def _compose_fill_reply(
    document: DocumentView, filled: tuple[str, ...], rejected: tuple[FieldError, ...]
) -> str:
    labels = {spec.key: spec.label for spec in document.template.fields}
    parts: list[str] = []
    if filled:
        parts.append("Заполнил: " + ", ".join(labels[key] for key in filled) + ".")
    else:
        parts.append("В сообщении не нашёл значений для полей документа.")
    if rejected:
        parts.append("Не принял: " + "; ".join(error.message for error in rejected) + ".")
    if document.missing:
        parts.append("Ещё нужно: " + ", ".join(labels[key] for key in document.missing) + ".")
    if document.unconfirmed:
        parts.append("Проверьте заполненное и подтвердите.")
    return " ".join(parts)


async def fill_from_message(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    message: str,
    llm: LLMClient | None,
) -> AgentFillResult:
    model = _require(llm)
    document = await get_document(session, user_id=user_id, document_id=document_id)
    fields = document.template.fields
    prompt = (
        f"{FILL_INSTRUCTIONS}\n\nПоля документа «{document.template.title}»:\n"
        f"{describe_fields(fields)}\n\nУже заполнено:\n{current_values(fields, document.values)}"
    )
    try:
        raw = await model.complete_json(
            [ChatMessage("system", prompt), ChatMessage("user", message)],
            schema=fields_schema(fields),
        )
    except LLMError as exc:
        raise _map_llm_error(exc) from exc

    known = {spec.key for spec in fields}
    proposals = {
        key: FieldValue(str(value).strip(), ValueSource.AGENT, confirmed=False)
        for key, value in raw.items()
        if key in known and str(value).strip()
    }
    updated = await set_fields(session, user_id=user_id, document_id=document_id, values=proposals)
    filled = tuple(key for key in proposals if key in updated.values)
    rejected = tuple(error for error in updated.errors if error.key in proposals)
    return AgentFillResult(
        document=updated,
        filled=filled,
        rejected=rejected,
        reply=_compose_fill_reply(updated, filled, rejected),
    )


async def answer_question(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    question: str,
    llm: LLMClient | None,
) -> str:
    model = _require(llm)
    document = await get_document(session, user_id=user_id, document_id=document_id)
    try:
        answer = await model.complete(
            [
                ChatMessage("system", f"{ASK_INSTRUCTIONS}\n\n{describe_document(document)}"),
                ChatMessage("user", question),
            ],
            max_tokens=MAX_ANSWER_TOKENS,
        )
    except LLMError as exc:
        raise _map_llm_error(exc) from exc
    return answer.strip()


async def draft_cover_letter(
    session: AsyncSession, *, user_id: int, document_id: int, llm: LLMClient | None
) -> str:
    model = _require(llm)
    document = await get_document(session, user_id=user_id, document_id=document_id)
    try:
        text = await model.complete(
            [
                ChatMessage("system", COVER_INSTRUCTIONS),
                ChatMessage("user", describe_document(document)),
            ],
            max_tokens=MAX_ANSWER_TOKENS,
        )
    except LLMError as exc:
        raise _map_llm_error(exc) from exc
    return text.strip()
