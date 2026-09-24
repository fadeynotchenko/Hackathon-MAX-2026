"""Распознавание фото, сканов и голосовых: те же поля, что у формы и сообщения.

Файл уходит модели вложением и у нас нигде не сохраняется — в документе остаются
только значения. Распознанное хранится с источником ``ocr``, строкой, с которой
его прочитали, и без подтверждения: готовым документ станет, когда человек
сверит значения с оригиналом и скажет «всё верно».

Уже подтверждённое (ручной ввод, профиль, карточка контрагента, одобренное
раньше) фото не перезаписывает: снимок чужой карточки не должен тихо подменить
реквизиты продавца. Расхождение показывается человеку, решает он.

Голосовое сначала расшифровывается, дальше это обычное сообщение: тот же разбор,
те же проверки, то же подтверждение.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import (
    FieldError,
    FieldSpec,
    FieldValue,
    ValueSource,
    normalize,
    validate_fields,
)
from core.domain.exceptions import AppError
from core.domain.media import AUDIBLE, READABLE, MediaType, require_media
from core.llm import Attachment, ChatMessage, LLMClient, LLMError, LLMInputError
from core.usecases.agent.prompts import (
    RECOGNIZE_INSTRUCTIONS,
    REQUISITES_INSTRUCTIONS,
    TRANSCRIBE_INSTRUCTIONS,
    TRANSCRIPT_SCHEMA,
    current_values,
    describe_fields,
    recognition_schema,
)
from core.usecases.agent.service import (
    AgentFillResult,
    compose_fill_reply,
    fill_from_message,
    map_llm_error,
    require_llm,
    written_keys,
)
from core.usecases.documents import DocumentView, get_document, set_fields
from core.usecases.documents.requisites import REQUISITE_FIELDS

FRAGMENT_MAX_LENGTH = 300
TRANSCRIPT_MAX_LENGTH = 4000
DEFAULT_REQUEST = "Перенеси значения из вложения."
VOICE_UNREADABLE_TEXT = "Голосовое не получилось прочитать. Запишите ещё раз или напишите текстом"


@dataclass(frozen=True)
class RecognizedRequisites:
    """Реквизиты с фото для формы карточки: ничего не сохранено, решает человек."""

    kind: str
    values: dict[str, FieldValue]
    errors: tuple[FieldError, ...]


@dataclass(frozen=True)
class VoiceFillResult:
    transcript: str
    fill: AgentFillResult


@dataclass(frozen=True)
class _Reading:
    kind: str
    values: dict[str, FieldValue]


def _attachment(data: bytes, media: MediaType, stem: str) -> Attachment:
    return Attachment(data=data, media_type=media.mime, filename=f"{stem}.{media.extension}")


def _confidence(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return min(max(value, 0.0), 1.0)


def _parse(raw: Mapping[str, Any], fields: tuple[FieldSpec, ...]) -> _Reading:
    known = {spec.key for spec in fields}
    values: dict[str, FieldValue] = {}
    items = raw.get("values")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", ""))
        value = str(item.get("value", "")).strip()
        if key not in known or not value:
            continue
        fragment = str(item.get("fragment", "")).strip()[:FRAGMENT_MAX_LENGTH]
        candidate = FieldValue(
            value,
            ValueSource.OCR,
            confidence=_confidence(item.get("confidence")),
            confirmed=False,
            fragment=fragment or None,
        )
        previous = values.get(key)
        # Одно поле модель иногда называет дважды (ИНН в шапке и в подписи): берём уверенное.
        if previous is None or (candidate.confidence or 0) > (previous.confidence or 0):
            values[key] = candidate
    return _Reading(kind=str(raw.get("kind", "")).strip()[:100], values=values)


async def _read(
    model: LLMClient,
    *,
    instructions: str,
    context: str,
    request: str,
    attachment: Attachment,
    fields: tuple[FieldSpec, ...],
) -> _Reading:
    try:
        raw = await model.complete_json(
            [
                ChatMessage("system", f"{instructions}\n\n{context}"),
                ChatMessage("user", request.strip() or DEFAULT_REQUEST, (attachment,)),
            ],
            schema=recognition_schema(fields),
        )
    except LLMError as exc:
        raise map_llm_error(exc) from exc
    return _parse(raw, fields)


def _conflicts(document: DocumentView, reading: _Reading, protected: set[str]) -> tuple[str, ...]:
    """Подтверждённые поля, для которых во вложении стоит другое корректное значение."""
    specs = {spec.key: spec for spec in document.template.fields}
    out: list[str] = []
    for key, proposal in reading.values.items():
        if key not in protected:
            continue
        normalized, error = normalize(specs[key], proposal.value)
        if error is None and normalized and normalized != document.values[key].value:
            out.append(key)
    return tuple(out)


async def fill_from_file(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    data: bytes,
    llm: LLMClient | None,
    max_bytes: int,
    request: str = "",
) -> AgentFillResult:
    """Фото или скан (JPG, PNG, PDF, DOCX) → значения полей документа на подтверждение.

    ``request`` — слова пользователя рядом с файлом (подпись к фото в чате):
    «это реквизиты покупателя» решает, в чью сторону класть значения."""
    model = require_llm(llm)
    media = require_media(data, kinds=READABLE, max_bytes=max_bytes)
    document = await get_document(session, user_id=user_id, document_id=document_id)
    fields = document.template.fields
    reading = await _read(
        model,
        instructions=RECOGNIZE_INSTRUCTIONS,
        context=(
            f"Поля документа «{document.template.title}»:\n{describe_fields(fields)}\n\n"
            f"Уже заполнено:\n{current_values(fields, document.values)}"
        ),
        request=request,
        attachment=_attachment(data, media, "document"),
        fields=fields,
    )

    protected = {key for key, value in document.values.items() if value.confirmed}
    proposals = {key: v for key, v in reading.values.items() if key not in protected}
    updated = document
    if proposals:
        updated = await set_fields(
            session, user_id=user_id, document_id=document_id, values=proposals
        )
    rejected = tuple(error for error in updated.errors if error.key in proposals)
    filled = written_keys(proposals, updated, rejected)
    kept = _conflicts(document, reading, protected)
    reply = compose_fill_reply(updated, filled, rejected, kept=kept, source="Во вложении")
    if reading.kind:
        reply = f"Во вложении — {reading.kind}. {reply}"
    return AgentFillResult(
        document=updated,
        filled=filled,
        rejected=rejected,
        reply=reply,
        kind=reading.kind,
        kept=kept,
    )


async def recognize_requisites(
    *, data: bytes, llm: LLMClient | None, max_bytes: int, request: str = ""
) -> RecognizedRequisites:
    """Реквизиты организации с фото для формы контрагента или своей компании.

    Ничего не сохраняет: форма показывает значения рядом со строками, из которых
    они прочитаны, а записывает карточку обычный путь после проверки человеком."""
    model = require_llm(llm)
    media = require_media(data, kinds=READABLE, max_bytes=max_bytes)
    reading = await _read(
        model,
        instructions=REQUISITES_INSTRUCTIONS,
        context=f"Поля карточки:\n{describe_fields(REQUISITE_FIELDS)}",
        request=request,
        attachment=_attachment(data, media, "requisites"),
        fields=REQUISITE_FIELDS,
    )
    validated = validate_fields(REQUISITE_FIELDS, reading.values)
    return RecognizedRequisites(reading.kind, validated.values, validated.errors)


async def transcribe(*, data: bytes, llm: LLMClient | None, max_bytes: int) -> str:
    """Голосовое → текст. Пустая расшифровка — ошибка, а не пустое сообщение помощнику."""
    model = require_llm(llm)
    try:
        media = require_media(data, kinds=AUDIBLE, max_bytes=max_bytes)
    except AppError as exc:
        if exc.code != "media.unsupported":
            raise
        raise AppError(VOICE_UNREADABLE_TEXT, code=exc.code, status_code=exc.status_code) from exc
    try:
        raw = await model.complete_json(
            [
                ChatMessage("system", TRANSCRIBE_INSTRUCTIONS),
                ChatMessage(
                    "user", "Голосовое сообщение во вложении.", (_attachment(data, media, "voice"),)
                ),
            ],
            schema=TRANSCRIPT_SCHEMA,
        )
    except LLMInputError as exc:
        # Тексты про «фото JPG или PNG» к голосовому не подходят.
        raise AppError(
            VOICE_UNREADABLE_TEXT, code="media.rejected", status_code=415, log_message=str(exc)
        ) from exc
    except LLMError as exc:
        raise map_llm_error(exc) from exc
    text = str(raw.get("text", "")).strip()
    if not text:
        raise AppError(
            "Не расслышал: в голосовом нет речи. Повторите или напишите текстом",
            code="agent.voice_empty",
            status_code=422,
        )
    return text[:TRANSCRIPT_MAX_LENGTH]


async def fill_from_voice(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    data: bytes,
    llm: LLMClient | None,
    max_bytes: int,
) -> VoiceFillResult:
    # Чужой или удалённый документ — 404 до модели: голосовое не уходит к провайдеру зря.
    await get_document(session, user_id=user_id, document_id=document_id)
    transcript = await transcribe(data=data, llm=llm, max_bytes=max_bytes)
    fill = await fill_from_message(
        session, user_id=user_id, document_id=document_id, message=transcript, llm=llm
    )
    return VoiceFillResult(transcript=transcript, fill=fill)
