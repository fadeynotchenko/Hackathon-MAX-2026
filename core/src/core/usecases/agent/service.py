"""Сценарии агента: заполнить поля из сообщения, ответить по документу, написать письмо.

Каналонейтральны, как и остальные сценарии: их одинаково зовёт ручка мини-аппа и
обработчик сообщения бота. Всё, что предлагает модель, проходит через те же
``set_fields`` и доменную проверку, что и ручной ввод, и сохраняется с
источником ``agent`` без подтверждения — готовым документ станет, когда человек
скажет «всё верно».
"""

from __future__ import annotations

import re
from collections.abc import Mapping
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
    missing_in_order,
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
    # Для ответа в чате: что во вложении и какие подтверждённые значения фото
    # не перезаписало, потому что на нём другое.
    kind: str = ""
    kept: tuple[str, ...] = ()
    # Значения, которые в документе уже такие же: «ничего не поменял», а не «не нашёл».
    unchanged: tuple[str, ...] = ()


def stems(text: str) -> set[str]:
    # «Семенов» и «Семёнов» — одно слово: ё пишут не все, и модель тоже.
    words = _WORD.findall(text.lower().replace("ё", "е"))
    return {word[:_MIN_WORD] for word in words if len(word) >= _MIN_WORD}


def lower_first(label: str) -> str:
    """«Номер счёта» → «номер счёта» посреди фразы; «ИНН клиента» и «НДС» — как есть."""
    if len(label) > 1 and label[1].islower():
        return label[0].lower() + label[1:]
    return label


def missing_labels(document: DocumentView) -> list[str]:
    """Названия пустых полей в порядке формы: «Название клиента», «Дата счёта»."""
    labels = {spec.key: spec.label for spec in document.template.fields}
    return [labels[key] for key in missing_in_order(document)]


def missing_text(document: DocumentView) -> str:
    return ", ".join(lower_first(label) for label in missing_labels(document))


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
        "Не получилось разобрать ответ помощника, пришлите ещё раз",
        code="agent.bad_response",
        status_code=502,
        log_message=str(exc),
    )


def written_keys(
    proposals: Mapping[str, FieldValue], updated: DocumentView, rejected: tuple[FieldError, ...]
) -> tuple[str, ...]:
    """Что действительно записано. Отклонённое значение оставляет в документе
    прежнее — поле заполнено, но не этим предложением."""
    refused = {error.key for error in rejected}
    return tuple(key for key in proposals if key in updated.values and key not in refused)


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
        parts.append("Заполнил: " + ", ".join(lower_first(labels[key]) for key in filled) + ".")
    elif not rejected:
        parts.append(f"{source} не нашёл значений для полей документа.")
    if kept:
        parts.append(
            "Не стал менять — во вложении другое: "
            + ", ".join(lower_first(labels[key]) for key in kept)
            + "."
        )
    if rejected:
        parts.append("Не записал: " + "; ".join(error.message for error in rejected) + ".")
    if document.missing:
        parts.append(f"Ещё нужно: {missing_text(document)}.")
    if document.unconfirmed:
        parts.append("Проверьте и подтвердите.")
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
        f"Ещё не заполнено:\n{missing_fields(fields, missing_in_order(document))}"
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
    unchanged: list[str] = []
    for key, value in raw.items():
        text = str(value).strip()
        if key not in specs or not text:
            continue
        # Модель повторяет значения из «Уже заполнено»: без этой проверки реквизиты
        # из профиля переписывались бы с источником «помощник» и снова ждали подтверждения.
        if not grounded(specs[key], text, message):
            continue
        previous = document.values.get(key)
        if previous is not None and normalize(specs[key], text)[0] == previous.value:
            unchanged.append(key)
            continue
        proposals[key] = FieldValue(text, ValueSource.AGENT, confirmed=False)
    updated = await set_fields(session, user_id=user_id, document_id=document_id, values=proposals)
    rejected = tuple(error for error in updated.errors if error.key in proposals)
    filled = written_keys(proposals, updated, rejected)
    return AgentFillResult(
        document=updated,
        filled=filled,
        rejected=rejected,
        reply=compose_fill_reply(updated, filled, rejected),
        unchanged=tuple(unchanged),
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
    return _not_empty(answer)


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
    return _not_empty(text)


def _not_empty(text: str) -> str:
    """Пустой ответ модели — сбой, а не ответ: пустое сообщение в чат не уйдёт
    (контракт notify.user его не пропустит), и человек остался бы без ответа."""
    if not text.strip():
        raise AppError(
            "Помощник не нашёл, что ответить. Спросите по-другому",
            code="agent.empty_answer",
            status_code=502,
        )
    return text.strip()
