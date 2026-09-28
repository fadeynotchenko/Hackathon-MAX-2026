"""Документ по присланному файлу: поменять данные, сохранив оформление.

Человек присылает документ, которого нет в каталоге, — договор от партнёра,
свой прошлый счёт, анкету, бланк. Места для данных ищутся так же, как для
своего шаблона из образца (метки, помощник, правила по тексту); из них
получается шаблон, скрытый из каталога, и сразу документ на нём, где значения
полей — то, что стоит в файле сейчас. Дальше документ живёт как любой другой:
значения правятся формой в мини-аппе или сообщением боту, проверяются теми
же правилами, а файл собирается в копии присланного — меняются только места.

PDF собирается на его же листе: значения меняются поверх исходных
(core.files.pdf_overlay); DOCX по такому документу — текстовый.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldType, FieldValue, ValueSource
from core.domain.exceptions import AppError, ValidationError
from core.domain.places import apply_places, place_spans
from core.llm import LLMClient
from core.usecases.agent.template_import import (
    FOUND_NONE,
    ImportedField,
    TemplateImport,
    import_template_file,
)
from core.usecases.documents import (
    REQUISITE_FIELDS,
    DocumentView,
    TemplateField,
    TemplateInput,
    create_from_values,
    create_hidden_template,
)
from core.usecases.documents.requisites import CLIENT_PREFIX, SELLER_PREFIX

_SIDES = {SELLER_PREFIX: "продавца", CLIENT_PREFIX: "клиента"}
_CATALOG_LABELS = {
    "number": ("Номер документа", FieldType.TEXT),
    "date": ("Дата документа", FieldType.DATE),
    "total": ("Сумма", FieldType.MONEY),
} | {
    f"{prefix}{spec.key}": (f"{spec.label} {side}", spec.type)
    for prefix, side in _SIDES.items()
    for spec in REQUISITE_FIELDS
}


@dataclass(frozen=True)
class DocumentFromFile:
    document: DocumentView
    format: str
    found_by: str
    notice: str | None


def _reachable(imported: Sequence[ImportedField], lines: Sequence[str]) -> list[ImportedField]:
    """Поле, чьё место целиком внутри чужого, более длинного, в документе не
    заменилось бы ни разу: его не показываем, иначе правка ничего не меняла бы."""
    places = [(str(index), place) for index, item in enumerate(imported) for place in item.places]
    hit = {key for line in lines for _, _, key in place_spans(line, places)}
    return [item for index, item in enumerate(imported) if str(index) in hit]


def _fields(imported: Sequence[ImportedField]) -> list[tuple[TemplateField, str]]:
    """Поля шаблона и значения из файла. Реквизит из каталога называется как в
    каталоге («ИНН клиента»), своё поле получает ключ ``field_N``; одинаковые
    названия различаются номером — иначе шаблон не сохранится."""
    out: list[tuple[TemplateField, str]] = []
    labels: set[str] = set()
    keys: set[str] = set()
    for number, item in enumerate(imported, 1):
        key, label, field_type = item.key, item.label, item.type
        if key in _CATALOG_LABELS and key not in keys:
            label, field_type = _CATALOG_LABELS[key]
        else:
            key = f"field_{number}"
        name, n = label, 1
        while name.casefold() in labels:
            n += 1
            name = f"{label} ({n})"
        labels.add(name.casefold())
        keys.add(key)
        field = TemplateField(
            key=key,
            label=name,
            type=field_type,
            required=item.required,
            carry_over=key not in ("number", "date"),
            places=item.places,
        )
        out.append((field, item.value))
    return out


def _text_body(found: TemplateImport, fields: Sequence[TemplateField]) -> str:
    places = [(field.key, place) for field in fields for place in field.places]
    return "\n".join(apply_places(line, places) for line in found.text.split("\n")).strip()


async def document_from_file(
    session: AsyncSession,
    *,
    user_id: int,
    data: bytes,
    filename: str,
    llm: LLMClient | None,
    max_bytes: int,
) -> DocumentFromFile:
    found = await import_template_file(
        session, user_id=user_id, data=data, filename=filename, llm=llm, max_bytes=max_bytes
    )
    if found.found_by == FOUND_NONE:
        raise AppError(
            "В файле не нашлось мест для данных. Поставьте в файле метки "
            "{{Название поля}} там, где меняются значения, и пришлите его снова",
            code="document.import_empty",
            status_code=422,
        )
    pairs = _fields(_reachable(found.fields, found.text.split("\n")))
    fields = tuple(field for field, _ in pairs)
    try:
        template = await create_hidden_template(
            session,
            user_id=user_id,
            data=TemplateInput(
                title=found.title,
                description=f"По файлу «{found.filename}»"[:300],
                body="" if found.file_id is not None else _text_body(found, fields),
                fields=fields,
                file_id=found.file_id,
                kind=found.kind,
            ),
        )
    except ValidationError as exc:
        # Места нашлись, но шаблон из них не сложился — это разбор файла, а не
        # ошибка человека: говорим, что делать, подробности — в лог.
        raise AppError(
            "Не получилось разобрать места для данных в этом файле — поставьте в нём "
            "метки {{Название поля}} и пришлите снова",
            code="document.import_failed",
            status_code=422,
            log_message=str(exc),
        ) from exc
    values = {
        field.key: FieldValue(value, source=ValueSource.FILE) for field, value in pairs if value
    }
    document = await create_from_values(session, user_id=user_id, template=template, values=values)
    return DocumentFromFile(document, found.format, found.found_by, found.notice)
