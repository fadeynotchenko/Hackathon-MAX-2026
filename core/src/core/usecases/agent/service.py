"""Сценарии агента: заполнить поля из сообщения, ответить по документу, написать письмо.

Каналонейтральны, как и остальные сценарии: их одинаково зовёт ручка мини-аппа и
обработчик сообщения бота. Всё, что предлагает модель, проходит через те же
``set_fields`` и доменную проверку, что и ручной ввод, и сохраняется с
источником ``agent`` без подтверждения — готовым документ станет, когда человек
скажет «всё верно».
"""

from __future__ import annotations

import json
import logging
import re
import time
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
    parse_items,
)
from core.domain.exceptions import AppError
from core.llm import ChatMessage, LLMClient, LLMError, LLMInputError, LLMUnavailableError
from core.logs import biz_info, biz_warn
from core.suggest import SuggestClient, SuggestUnavailableError
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
from core.usecases.documents import (
    DocumentView,
    agent_outcome,
    get_document,
    record_agent_run,
    set_fields,
)

MAX_ANSWER_TOKENS = 600

logger = logging.getLogger(__name__)

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
    # Подставлено из реестра по названному ИНН, а не взято из слов человека.
    registry: tuple[str, ...] = ()


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
        # Без цифр («нет», «не указан») реквизита нет вовсе: пустая строка нашлась
        # бы в любом сообщении, и человек увидел бы «Не записал: ИНН …» ни о чём.
        digits = re.sub(r"\D", "", value)
        return bool(digits) and digits in re.sub(r"\D", "", message)
    if spec.type is FieldType.ITEMS:
        # Список опирается на сообщение, если в нём названа хоть одна позиция:
        # прежние позиции модель возвращает вместе с новой, так и задумано.
        items, _problem = parse_items(value)
        return not items or bool(stems(" ".join(item.name for item in items)) & stems(message))
    if spec.type in _WORDED:
        value_stems = stems(value)
        return not value_stems or bool(value_stems & stems(message))
    return True


def _as_text(value: object) -> str:
    """Значение из ответа модели строкой: список позиций приходит массивом."""
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False) if value else ""
    return str(value).strip()


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


# Что реестр знает об организации по ИНН и что из этого кладём в поля стороны.
_REGISTRY_FIELDS = ("name", "kpp", "ogrn", "address", "director")
_SIDES = ("client_", "seller_")


async def registry_values(
    suggest: SuggestClient | None,
    fields: tuple[FieldSpec, ...],
    document: DocumentView,
    proposals: Mapping[str, FieldValue],
) -> dict[str, FieldValue]:
    """Реквизиты стороны из реестра по ИНН, который человек назвал в сообщении.

    «Счёт для ИНН 7707083893» — и название, КПП, адрес клиента не нужно диктовать.
    Подставляется только пустое: названное человеком и уже записанное реестр не
    перебивает. Значения ждут подтверждения, как всё от помощника. Реестр
    молчит — поля остаются пустыми, заполнение от этого не падает."""
    if suggest is None:
        return {}
    keys = {spec.key for spec in fields}
    found: dict[str, FieldValue] = {}
    for prefix in _SIDES:
        named = proposals.get(f"{prefix}inn")
        inn = re.sub(r"\D", "", named.value) if named is not None else ""
        if not inn:
            continue
        try:
            records = await suggest.companies(inn, count=1)
        except SuggestUnavailableError as exc:
            biz_warn(logger, "agent.fill.registry_failed", error=str(exc))
            continue
        record = next((record for record in records if record.inn == inn), None)
        if record is None:
            continue
        for name in _REGISTRY_FIELDS:
            key, value = f"{prefix}{name}", str(getattr(record, name))
            if key in keys and value and key not in proposals and key not in document.values:
                found[key] = FieldValue(value, ValueSource.AGENT, confirmed=False)
    return found


def compose_fill_reply(
    document: DocumentView,
    filled: tuple[str, ...],
    rejected: tuple[FieldError, ...],
    *,
    kept: tuple[str, ...] = (),
    source: str = "В сообщении",
    registry: tuple[str, ...] = (),
) -> str:
    labels = {spec.key: spec.label for spec in document.template.fields}
    parts: list[str] = []
    if filled:
        parts.append("Заполнил: " + ", ".join(lower_first(labels[key]) for key in filled) + ".")
    if registry:
        parts.append(
            "Из реестра по ИНН: " + ", ".join(lower_first(labels[key]) for key in registry) + "."
        )
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


def fill_messages(
    title: str,
    fields: tuple[FieldSpec, ...],
    values: Mapping[str, FieldValue],
    missing: tuple[str, ...],
    message: str,
) -> list[ChatMessage]:
    """Запрос модели на заполнение: правила, поля, что уже есть и чего нет.
    Отдельно от сценария — те же сообщения гоняет набор проверочных примеров."""
    prompt = (
        f"{fill_instructions()}\n\nПоля документа «{title}»:\n"
        f"{describe_fields(fields)}\n\nУже заполнено:\n{current_values(fields, values)}\n\n"
        f"Ещё не заполнено:\n{missing_fields(fields, missing)}"
    )
    return [ChatMessage("system", prompt), ChatMessage("user", message)]


@dataclass(frozen=True)
class Proposed:
    values: dict[str, FieldValue]
    unchanged: list[str]
    ungrounded: list[str]


def propose(
    raw: Mapping[str, object],
    fields: tuple[FieldSpec, ...],
    values: Mapping[str, FieldValue],
    message: str,
) -> Proposed:
    """Ответ модели → значения на запись: известные поля, опора на слова
    человека, без повторов того, что в документе уже так."""
    specs = {spec.key: spec for spec in fields}
    proposals: dict[str, FieldValue] = {}
    unchanged: list[str] = []
    ungrounded: list[str] = []
    for key, value in raw.items():
        text = _as_text(value)
        if key not in specs or not text:
            continue
        # Модель повторяет значения из «Уже заполнено»: без этой проверки реквизиты
        # из профиля переписывались бы с источником «помощник» и снова ждали подтверждения.
        if not grounded(specs[key], text, message):
            ungrounded.append(key)
            continue
        previous = values.get(key)
        if previous is not None and normalize(specs[key], text)[0] == previous.value:
            unchanged.append(key)
            continue
        proposals[key] = FieldValue(text, ValueSource.AGENT, confirmed=False)
    return Proposed(proposals, unchanged, ungrounded)


async def fill_from_message(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    message: str,
    llm: LLMClient | None,
    suggest: SuggestClient | None = None,
    channel: str = "text",
) -> AgentFillResult:
    model = require_llm(llm)
    document = await get_document(session, user_id=user_id, document_id=document_id)
    fields = document.template.fields
    started = time.monotonic()
    try:
        raw = await model.complete_json(
            fill_messages(
                document.template.title,
                fields,
                document.values,
                missing_in_order(document),
                message,
            ),
            schema=fields_schema(fields),
        )
    except LLMError as exc:
        raise map_llm_error(exc) from exc
    duration_ms = int((time.monotonic() - started) * 1000)

    proposed = propose(raw, fields, document.values, message)
    proposals, unchanged, ungrounded = proposed.values, proposed.unchanged, proposed.ungrounded
    found = await registry_values(suggest, fields, document, proposals)
    proposals |= found
    updated = await set_fields(session, user_id=user_id, document_id=document_id, values=proposals)
    rejected = tuple(error for error in updated.errors if error.key in proposals)
    filled = written_keys(proposals, updated, rejected)
    registry = tuple(key for key in filled if key in found)
    # Только ключи, без значений: в значениях реквизиты и имена. По логу видно,
    # что модель додумывает или что проверка опоры режет законное значение.
    biz_info(
        logger,
        "agent.fill.done",
        document_id=document_id,
        filled=list(filled),
        rejected=[error.key for error in rejected],
        ungrounded=ungrounded,
        unchanged=unchanged,
        registry=list(registry),
    )
    await record_agent_run(
        session,
        user_id=user_id,
        channel=channel,
        outcome=agent_outcome(written=bool(filled or unchanged), lost=bool(rejected or ungrounded)),
        duration_ms=duration_ms,
        document_id=document_id,
        template_kind=document.template.kind,
    )
    return AgentFillResult(
        document=updated,
        filled=filled,
        rejected=rejected,
        reply=compose_fill_reply(updated, filled, rejected, registry=registry),
        unchanged=tuple(unchanged),
        registry=registry,
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
