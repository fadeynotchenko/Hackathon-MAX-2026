"""Сценарии агента: заполнить поля из сообщения, ответить по документу, написать письмо.

Каналонейтральны, как и остальные сценарии: их одинаково зовёт ручка мини-аппа и
обработчик сообщения бота. Всё, что предлагает модель, проходит через те же
``set_fields`` и доменную проверку, что и ручной ввод, и сохраняется с
источником ``agent`` без подтверждения — готовым документ станет, когда человек
скажет «всё верно».
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import (
    FieldError,
    FieldSpec,
    FieldType,
    FieldValue,
    ValueSource,
    normalize,
)
from core.domain.exceptions import AppError
from core.llm import ChatMessage, LLMClient, LLMError, LLMInputError, LLMUnavailableError
from core.usecases.agent.prompts import (
    ASK_INSTRUCTIONS,
    COVER_INSTRUCTIONS,
    current_values,
    describe_document,
    describe_fields,
    fields_schema,
    fill_instructions,
    missing_fields,
)
from core.usecases.documents import DocumentView, get_document, set_fields

MAX_ANSWER_TOKENS = 600

_WORD = re.compile(r"[0-9a-zа-яё]+")
# Слова короче — «ооо», «ип», «г», «ул»: по ним опору в сообщении не проверить.
_MIN_WORD = 4
_WORDED = frozenset(
    {FieldType.TEXT, FieldType.MULTILINE, FieldType.NAME, FieldType.ADDRESS, FieldType.EMAIL}
)
_DIGITS_ONLY = frozenset(
    {FieldType.INN, FieldType.KPP, FieldType.OGRN, FieldType.BIC, FieldType.ACCOUNT}
)


@dataclass(frozen=True)
class AgentFillResult:
    document: DocumentView
    filled: tuple[str, ...]
    rejected: tuple[FieldError, ...]
    reply: str


def stems(text: str) -> set[str]:
    return {word[:_MIN_WORD] for word in _WORD.findall(text.lower()) if len(word) >= _MIN_WORD}


def grounded(spec: FieldSpec, value: str, message: str) -> bool:
    """Значение опирается на слова пользователя, а не выведено моделью из контекста.

    Правило «не придумывай» в инструкции GigaChat нарушал: вписывал город из адреса
    продавца, которого в сообщении не было. Текст должен разделять с сообщением хотя
    бы одно слово (по первым буквам — падежи меняют окончание), реквизит — цифры.
    Даты, суммы и сроки не проверяются: «сегодня» и «200к» законно пишутся иначе."""
    if spec.type in _DIGITS_ONLY:
        return re.sub(r"\D", "", value) in re.sub(r"\D", "", message)
    if spec.type in _WORDED:
        value_stems = stems(value)
        return not value_stems or bool(value_stems & stems(message))
    return True


def require_llm(llm: LLMClient | None) -> LLMClient:
    if llm is None:
        raise AppError(
            "Помощник сейчас выключен, заполните поля вручную",
            code="agent.unavailable",
            status_code=503,
        )
    return llm


def map_llm_error(exc: LLMError) -> AppError:
    if isinstance(exc, LLMInputError):
        return AppError(
            "Файл не удалось прочитать: пришлите фото JPG или PNG, PDF или DOCX",
            code="media.rejected",
            status_code=415,
            log_message=str(exc),
        )
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


def compose_fill_reply(
    document: DocumentView,
    filled: tuple[str, ...],
    rejected: tuple[FieldError, ...],
    *,
    kept: tuple[str, ...] = (),
    source: str = "В сообщении",
) -> str:
    labels = {spec.key: spec.label for spec in document.template.fields}
    parts: list[str] = []
    if filled:
        parts.append("Заполнил: " + ", ".join(labels[key] for key in filled) + ".")
    else:
        parts.append(f"{source} не нашёл значений для полей документа.")
    if kept:
        parts.append(
            "Оставил как было, хотя во вложении другое: "
            + ", ".join(labels[key] for key in kept)
            + "."
        )
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
    model = require_llm(llm)
    document = await get_document(session, user_id=user_id, document_id=document_id)
    fields = document.template.fields
    prompt = (
        f"{fill_instructions()}\n\nПоля документа «{document.template.title}»:\n"
        f"{describe_fields(fields)}\n\nУже заполнено:\n{current_values(fields, document.values)}\n\n"
        f"Ещё не заполнено:\n{missing_fields(fields, document.missing)}"
    )
    try:
        raw = await model.complete_json(
            [ChatMessage("system", prompt), ChatMessage("user", message)],
            schema=fields_schema(fields),
        )
    except LLMError as exc:
        raise map_llm_error(exc) from exc

    specs = {spec.key: spec for spec in fields}
    proposals: dict[str, FieldValue] = {}
    for key, value in raw.items():
        text = str(value).strip()
        if key not in specs or not text:
            continue
        # Модель повторяет значения из «Уже заполнено»: без этой проверки реквизиты
        # из профиля переписывались бы с источником «помощник» и снова ждали подтверждения.
        previous = document.values.get(key)
        if previous is not None and normalize(specs[key], text)[0] == previous.value:
            continue
        if not grounded(specs[key], text, message):
            continue
        proposals[key] = FieldValue(text, ValueSource.AGENT, confirmed=False)
    updated = await set_fields(session, user_id=user_id, document_id=document_id, values=proposals)
    filled = tuple(key for key in proposals if key in updated.values)
    rejected = tuple(error for error in updated.errors if error.key in proposals)
    return AgentFillResult(
        document=updated,
        filled=filled,
        rejected=rejected,
        reply=compose_fill_reply(updated, filled, rejected),
    )


async def answer_question(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    question: str,
    llm: LLMClient | None,
) -> str:
    model = require_llm(llm)
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
        raise map_llm_error(exc) from exc
    return answer.strip()


async def draft_cover_letter(
    session: AsyncSession, *, user_id: int, document_id: int, llm: LLMClient | None
) -> str:
    model = require_llm(llm)
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
        raise map_llm_error(exc) from exc
    return text.strip()
