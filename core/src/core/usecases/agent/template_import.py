"""Свой шаблон из файла-образца: найти в «рыбе» места для данных.

Пользователь присылает готовый документ (DOCX или PDF): КП клиенту, свой счёт,
фирменный бланк. Места для данных находятся двумя путями:

- метки, которые человек сам поставил в файле: ``{{Название клиента}}``;
- если меток нет — помощник показывает, какие фрагменты текста меняются от
  документа к документу (клиент, сумма, даты).

Помощник не переписывает документ: он называет фрагменты, а сервер оставляет
только те, что буквально есть в тексте файла. Итог — черновик шаблона, который
человек проверяет и сохраняет; ничего не сохраняется шаблоном без него.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import TemplateFileRepository
from core.domain.documents import FieldType
from core.domain.exceptions import AppError
from core.domain.media import DOCX, MediaKind, require_media
from core.domain.places import LABEL_MARKER, Place, found, label_of
from core.files import TemplateFileError, docx_lines, pdf_lines
from core.llm import ChatMessage, LLMClient, LLMError
from core.logs import biz_warn
from core.usecases.agent.prompts import TEMPLATE_PLACES_INSTRUCTIONS
from core.usecases.documents.templates import (
    CATALOG_KEYS,
    FIELDS_MAX,
    KINDS,
    LABEL_MAX,
    OTHER_KIND,
    PLACE_BEFORE_MAX,
    PLACE_MAX,
    TITLE_MAX,
    guess_kind,
    required_by_default,
    requisite_type,
)

logger = logging.getLogger(__name__)

# Столько текста образца уходит модели: деловой документ целиком, но не книга.
MAX_PROMPT_CHARS = 15_000
# Загруженный и брошенный образец живёт сутки: вдруг человек вернётся к экрану.
UNUSED_FILE_TTL = timedelta(days=1)
FOUND_BY_MARKERS = "markers"
FOUND_BY_ASSISTANT = "assistant"
FOUND_NONE = "none"
# Пустая линия «______» или «……» без текста перед ней — неизвестно, чья она.
_BLANK_LINE = re.compile(r"^[\s_.…-]+$")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class ImportedField:
    # Ключ каталога (реквизит, номер, дата, сумма) или пусто — своё поле.
    key: str
    label: str
    type: FieldType
    required: bool
    places: tuple[Place, ...]


@dataclass(frozen=True)
class TemplateImport:
    # Сохранённый образец DOCX; у PDF — None: шаблон из него будет текстовым.
    file_id: int | None
    filename: str
    format: str
    title: str
    text: str
    fields: tuple[ImportedField, ...]
    found_by: str
    notice: str | None = None
    # Вид документа: счёт, КП, договор или другой — человек может поменять.
    kind: str = OTHER_KIND


def _norm(label: str) -> str:
    return _SPACES.sub(" ", label.lower().replace("ё", "е")).strip()


def marker_fields(lines: Sequence[str]) -> list[ImportedField]:
    """Метки в файле: {{Название клиента}} — поле «Название клиента», место —
    сама метка, как она написана (с пробелами внутри скобок и без)."""
    places: dict[str, tuple[str, list[Place]]] = {}
    for line in lines:
        for match in LABEL_MARKER.finditer(line):
            label = label_of(match.group(0))[:LABEL_MAX]
            if not label:
                continue
            _, found_places = places.setdefault(_norm(label), (label, []))
            place = Place(match.group(0))
            if place not in found_places:
                found_places.append(place)
    return [
        ImportedField("", label, FieldType.TEXT, True, tuple(found_places))
        for label, found_places in list(places.values())[:FIELDS_MAX]
    ]


_PLACES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Вид документа: «Коммерческое предложение»"},
        "kind": {"type": "string", "enum": list(KINDS)},
        "places": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Фрагмент текста символ в символ"},
                    "before": {"type": "string", "description": "Текст перед фрагментом"},
                    "label": {"type": "string"},
                    "type": {"type": "string", "enum": [t.value for t in FieldType]},
                    "key": {"type": "string", "enum": [*sorted(CATALOG_KEYS), ""]},
                },
                "required": ["text", "before", "label", "type", "key"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "kind", "places"],
    "additionalProperties": False,
}


def _place(item: dict[str, Any], lines: Sequence[str]) -> Place | None:
    """Место из ответа модели — только если такой текст правда есть в файле."""
    text, before = str(item.get("text") or ""), str(item.get("before") or "")
    if not text.strip() or "\n" in text or len(text) > PLACE_MAX:
        return None
    if "\n" in before or len(before) > PLACE_BEFORE_MAX:
        before = ""
    if before and not found(lines, Place(text, before)):
        before = ""
    # Линия без подписи перед ней совпала бы со всеми линиями бланка сразу.
    if not before and _BLANK_LINE.match(text):
        return None
    place = Place(text, before)
    return place if found(lines, place) else None


def suggested_fields(raw: dict[str, Any], lines: Sequence[str]) -> list[ImportedField]:
    """Ответ модели → поля: одно название или ключ каталога — одно поле с
    несколькими местами; тип реквизита — по ключу, а не по словам модели."""
    grouped: dict[str, tuple[str, str, FieldType, list[Place]]] = {}
    items = raw.get("places")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        place = _place(item, lines)
        label = _SPACES.sub(" ", str(item.get("label") or "")).replace("{", "").replace("}", "")
        label = label.strip()[:LABEL_MAX]
        if place is None or not label:
            continue
        key = str(item.get("key") or "")
        key = key if key in CATALOG_KEYS else ""
        try:
            field_type = FieldType(str(item.get("type") or FieldType.TEXT))
        except ValueError:
            field_type = FieldType.TEXT
        field_type = requisite_type(key) or field_type
        group = key or _norm(label)
        _, _, _, places = grouped.setdefault(group, (key, label, field_type, []))
        if place not in places:
            places.append(place)
    return [
        ImportedField(
            key, label, field_type, required_by_default(key) if key else True, tuple(places)
        )
        for key, label, field_type, places in list(grouped.values())[:FIELDS_MAX]
    ]


def _title_from(filename: str) -> str:
    """«Фирменный_КП-2026.docx» → «Фирменный КП 2026»."""
    stem = PurePath(filename).stem
    return _SPACES.sub(" ", re.sub(r"[_\-]+", " ", stem)).strip()


async def import_template_file(
    session: AsyncSession,
    *,
    user_id: int,
    data: bytes,
    filename: str,
    llm: LLMClient | None,
    max_bytes: int,
) -> TemplateImport:
    media = require_media(data, kinds={MediaKind.DOCUMENT}, max_bytes=max_bytes)
    try:
        lines = docx_lines(data) if media is DOCX else pdf_lines(data)
    except TemplateFileError as exc:
        raise AppError(
            "В файле не нашлось текста. Пришлите DOCX или PDF, сохранённый из редактора, а не скан",
            code="template.file_unreadable",
            status_code=422,
            log_message=str(exc),
        ) from exc
    text = "\n".join(lines).strip("\n")
    if not text.strip():
        raise AppError("В файле нет текста", code="template.file_empty", status_code=422)

    title = ""
    kind = ""
    notice: str | None = None
    fields = marker_fields(lines)
    found_by = FOUND_BY_MARKERS if fields else FOUND_NONE
    if not fields and llm is None:
        notice = "Помощник выключен — отметьте места для данных сами"
    elif not fields and llm is not None:
        try:
            raw = await llm.complete_json(
                [
                    ChatMessage("system", TEMPLATE_PLACES_INSTRUCTIONS),
                    ChatMessage("user", text[:MAX_PROMPT_CHARS]),
                ],
                schema=_PLACES_SCHEMA,
            )
        except LLMError as exc:
            biz_warn(logger, "agent.template_import.llm_failed", error=str(exc))
            notice = "Помощник сейчас не ответил — отметьте места для данных сами"
        else:
            fields = suggested_fields(raw, lines)
            title = str(raw.get("title") or "").strip()
            kind = str(raw.get("kind") or "")
            found_by = FOUND_BY_ASSISTANT if fields else FOUND_NONE

    name = PurePath(filename).name[:255] or f"template.{media.extension}"
    file_id = None
    if media is DOCX:
        repo = TemplateFileRepository(session)
        await repo.delete_unused(user_id, before=datetime.now(UTC) - UNUSED_FILE_TTL)
        file_id = (await repo.create(owner_user_id=user_id, filename=name, data=data, text=text)).id
    title = (title or _title_from(name))[:TITLE_MAX]
    if kind not in KINDS:
        heading = [line for line in lines if line.strip()][:3]
        kind = guess_kind(title, name, *heading)
    return TemplateImport(
        file_id=file_id,
        filename=name,
        format=media.extension,
        title=title,
        text=text,
        fields=tuple(fields),
        found_by=found_by,
        notice=notice,
        kind=kind,
    )
