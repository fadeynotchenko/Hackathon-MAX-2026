"""Каталог шаблонов: встроенные заводятся при старте, свои делает пользователь.

Свой шаблон устроен как встроенный — текст с маркерами ``{{key}}`` и описание
полей, — поэтому заполнение, проверка, помощник и сборка файла работают с ним
без отдельной ветки. Реквизиты сторон узнаются по ключу (``seller_inn``,
``client_name``) и подставляются из организации и карточки клиента.

Шаблон из файла-образца DOCX хранит сам файл и места полей в нём (``places``):
текст шаблона сервер собирает из текста файла, а документ — в копии файла,
с логотипом и оформлением компании.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Template
from core.db.repositories import TemplateFileRepository, TemplateRepository
from core.domain.documents import FieldSpec, FieldType, fill_text_template, template_markers
from core.domain.exceptions import ForbiddenError, NotFoundError, ValidationError
from core.domain.places import Place, apply_places, found
from core.usecases.documents.builtin import BUILTIN_TEMPLATES, CLIENT, SELLER, SUBJECT
from core.usecases.documents.requisites import CLIENT_PREFIX, REQUISITE_FIELDS, SELLER_PREFIX

# Вид своего шаблона: в метриках свои шаблоны считаются отдельно от счетов и КП.
CUSTOM_KIND = "custom"
TEXT_FORMAT = "text"
DOCX_FORMAT = "docx"
# Название шаблона становится текстом кнопки в чате бота, а там предел — 64 символа.
TITLE_MAX = 64
DESCRIPTION_MAX = 300
BODY_MAX = 20_000
LABEL_MAX = 100
HINT_MAX = 200
FIELDS_MAX = 50
PLACE_MAX = 300
PLACE_BEFORE_MAX = 100
# Каталог и кнопки выбора в чате должны оставаться обозримыми.
OWN_TEMPLATES_MAX = 50
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_REQUISITE_TYPES = {spec.key: spec.type for spec in REQUISITE_FIELDS}
# Реквизиты, без которых сторона в документе не названа; остальные — по желанию.
_REQUIRED_REQUISITES = frozenset({"name", "inn"})
# Готовые ключи каталога: реквизиты сторон, номер, дата и сумма документа.
CATALOG_KEYS = frozenset(
    {
        f"{prefix}{spec.key}"
        for prefix in (SELLER_PREFIX, CLIENT_PREFIX)
        for spec in REQUISITE_FIELDS
    }
    | {"number", "date", "total"}
)


@dataclass(frozen=True)
class TemplateField(FieldSpec):
    """Поле шаблона. У шаблона из файла — ещё и места в образце, где стоит значение."""

    places: tuple[Place, ...] = ()


@dataclass(frozen=True)
class TemplateFileInfo:
    id: int
    filename: str
    # Текст образца (строка на абзац) — только когда шаблон открыт для правки.
    text: str | None = None


@dataclass(frozen=True)
class TemplateView:
    id: int
    slug: str
    title: str
    kind: str
    description: str
    body_format: str
    is_builtin: bool
    fields: tuple[TemplateField, ...]
    body: str
    file: TemplateFileInfo | None = None

    @property
    def preview(self) -> str:
        """Пустой бланк: так документ выглядит до первого заполненного поля."""
        return fill_text_template(self.body, {})

    @property
    def places(self) -> list[tuple[str, Place]]:
        return [(field.key, place) for field in self.fields for place in field.places]


@dataclass(frozen=True)
class TemplateInput:
    """Свой шаблон, как его прислал клиент. Раздел поля и тип реквизита
    сервер определяет сам по ключу. С ``file_id`` текст шаблона не
    присылается: его собирает сервер из образца и мест полей."""

    title: str
    description: str
    body: str
    fields: tuple[TemplateField, ...]
    file_id: int | None = None


def _specs_from_json(raw: list[dict[str, object]]) -> tuple[TemplateField, ...]:
    def places(item: dict[str, object]) -> tuple[Place, ...]:
        value = item.get("places")
        if not isinstance(value, list):
            return ()
        return tuple(
            Place(text=str(place.get("text", "")), before=str(place.get("before", "")))
            for place in value
            if isinstance(place, dict)
        )

    return tuple(
        TemplateField(
            key=str(item["key"]),
            label=str(item["label"]),
            type=FieldType(str(item.get("type", FieldType.TEXT))),
            required=bool(item.get("required", True)),
            group=str(item.get("group", "")),
            hint=str(item.get("hint", "")),
            max_length=int(item["max_length"]) if item.get("max_length") is not None else None,
            carry_over=bool(item.get("carry_over", True)),
            today_by_default=bool(item.get("today_by_default", False)),
            places=places(item),
        )
        for item in raw
    )


def _specs_to_json(specs: Iterable[FieldSpec]) -> list[dict[str, object]]:
    return [asdict(spec) | {"type": spec.type.value} for spec in specs]


def to_view(template: Template, *, file_text: str | None = None) -> TemplateView:
    file = template.file
    return TemplateView(
        id=template.id,
        slug=template.slug,
        title=template.title,
        kind=template.kind,
        description=template.description,
        body_format=template.body_format,
        is_builtin=template.owner_user_id is None,
        fields=_specs_from_json(template.fields),
        body=template.body,
        file=TemplateFileInfo(file.id, file.filename, file_text) if file is not None else None,
    )


async def ensure_builtin_templates(session: AsyncSession) -> int:
    """Идемпотентно записать встроенные шаблоны. Зовётся в lifespan после миграций:
    отдельный контейнер-сеятель для трёх шаблонов был бы дороже пользы."""
    repo = TemplateRepository(session)
    for template in BUILTIN_TEMPLATES:
        await repo.upsert_builtin(
            slug=template.slug,
            title=template.title,
            kind=template.kind,
            description=template.description,
            fields=_specs_to_json(template.fields),
            body=template.body,
            body_format=TEXT_FORMAT,
        )
    return len(BUILTIN_TEMPLATES)


async def list_templates(
    session: AsyncSession, *, user_id: int, slug: str | None = None
) -> list[TemplateView]:
    """Фильтр по слугу нужен клиентам, которые знают вид документа, но не его id:
    диплинк «создать счёт» и сценарий технической проверки."""
    templates = await TemplateRepository(session).list_available(user_id, slug=slug)
    return [to_view(t) for t in templates]


def _visible(template: Template | None, user_id: int) -> Template:
    if (
        template is None
        or template.archived_at is not None
        or (template.owner_user_id is not None and template.owner_user_id != user_id)
    ):
        raise NotFoundError("Шаблон не найден", code="template.not_found")
    return template


async def get_template(session: AsyncSession, *, user_id: int, template_id: int) -> TemplateView:
    """Шаблон целиком: у шаблона из файла — с текстом образца, чтобы его места
    можно было поправить."""
    template = _visible(await TemplateRepository(session).get(template_id), user_id)
    text = None
    if template.file_id is not None:
        text = await TemplateFileRepository(session).text(template.file_id)
    return to_view(template, file_text=text)


async def latest_template(session: AsyncSession, template: Template) -> TemplateView:
    """Шаблон для копии документа: прошлая редакция отсылает к живому шаблону,
    чтобы «на основе этого» брало исправленный текст. Удалённый шаблон копия
    не воскрешает в библиотеке, но и не ломается: остаётся текст документа."""
    if template.origin_id is not None:
        origin = await TemplateRepository(session).get(template.origin_id)
        if origin is not None and origin.archived_at is None:
            return to_view(origin)
    return to_view(template)


def field_group(key: str) -> str:
    if key.startswith(SELLER_PREFIX):
        return SELLER
    if key.startswith(CLIENT_PREFIX):
        return CLIENT
    return SUBJECT


def requisite_type(key: str) -> FieldType | None:
    """Реквизит стороны проверяется по своему типу, что бы ни прислал клиент:
    иначе «ИНН клиента» текстовым полем обходил бы контрольную сумму."""
    for prefix in (SELLER_PREFIX, CLIENT_PREFIX):
        if key.startswith(prefix):
            return _REQUISITE_TYPES.get(key.removeprefix(prefix))
    return None


def required_by_default(key: str) -> bool:
    """Обязательно ли поле, пока человек не решил сам: у ИП нет КПП, у клиента
    не всегда есть банк — из реквизитов обязательны только название и ИНН."""
    if requisite_type(key) is None:
        return True
    return key.split("_", 1)[1] in _REQUIRED_REQUISITES


def _marker(key: str) -> str:
    return "{{" + key + "}}"


def _quote(text: str) -> str:
    return f"«{text[:40]}…»" if len(text) > 40 else f"«{text}»"


def _clean_places(field: TemplateField, lines: Sequence[str], errors: list[str]) -> None:
    if not field.places:
        errors.append(f"«{field.label}»: укажите, где в файле стоит значение")
    for place in field.places:
        if not place.text.strip() or "\n" in place.text + place.before:
            errors.append(f"«{field.label}»: место в файле — фрагмент одной строки")
        elif len(place.text) > PLACE_MAX or len(place.before) > PLACE_BEFORE_MAX:
            errors.append(f"«{field.label}»: место в файле — не длиннее {PLACE_MAX} символов")
        elif not found(lines, place):
            errors.append(f"«{field.label}»: в файле нет текста {_quote(place.text)}")


def _clean(data: TemplateInput, file_lines: Sequence[str] | None = None) -> TemplateInput:
    """Проверить шаблон целиком и собрать все замечания в одно сообщение:
    человек правит шаблон на телефоне, и ошибки по одной стоили бы ему кругов.

    ``file_lines`` — текст образца: тогда текст шаблона собирается из него и
    мест полей, а присланный ``body`` не нужен."""
    errors: list[str] = []
    title = data.title.strip()
    if not title:
        errors.append("Назовите шаблон")
    elif len(title) > TITLE_MAX:
        errors.append(f"Название шаблона — не длиннее {TITLE_MAX} символов")
    description = data.description.strip()
    if len(description) > DESCRIPTION_MAX:
        errors.append(f"Описание — не длиннее {DESCRIPTION_MAX} символов")
    if len(data.fields) > FIELDS_MAX:
        errors.append(f"Полей в шаблоне — не больше {FIELDS_MAX}")

    fields: list[TemplateField] = []
    labels: set[str] = set()
    for spec in data.fields:
        label = spec.label.strip()
        if not _KEY.match(spec.key):
            errors.append(f"Поле «{label or spec.key}»: ключ из латинских букв, цифр и «_»")
        elif any(field.key == spec.key for field in fields):
            errors.append(f"Поле {_marker(spec.key)} описано дважды")
        elif not label:
            errors.append(f"У поля {_marker(spec.key)} нет названия")
        elif len(label) > LABEL_MAX:
            errors.append(f"Название поля «{label[:20]}…» — не длиннее {LABEL_MAX} символов")
        elif label.casefold() in labels:
            errors.append(f"Два поля называются «{label}»")
        else:
            labels.add(label.casefold())
            field_type = requisite_type(spec.key) or spec.type
            fields.append(
                TemplateField(
                    key=spec.key,
                    label=label,
                    type=field_type,
                    required=spec.required,
                    group=field_group(spec.key),
                    hint=spec.hint.strip()[:HINT_MAX],
                    carry_over=spec.carry_over,
                    today_by_default=spec.today_by_default and field_type is FieldType.DATE,
                    places=tuple(dict.fromkeys(spec.places)) if file_lines is not None else (),
                )
            )

    if file_lines is None:
        body = data.body.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not body:
            errors.append("Напишите текст шаблона")
        elif len(body) > BODY_MAX:
            errors.append(f"Текст шаблона — не длиннее {BODY_MAX} символов")
    else:
        for field in fields:
            _clean_places(field, file_lines, errors)
        places = [(field.key, place) for field in fields for place in field.places]
        body = "\n".join(apply_places(line, places) for line in file_lines).strip()

    used = template_markers(body)
    declared = {spec.key for spec in data.fields}
    errors.extend(
        f"В тексте есть поле {_marker(key)}, которого нет в списке полей"
        for key in used
        if key not in declared
    )
    errors.extend(
        f"Поле «{field.label}» не встречается в тексте"
        for field in fields
        if field.key not in used and (file_lines is None or field.places)
    )
    if body and not used and not fields:
        errors.append("Добавьте в текст хотя бы одно поле — иначе заполнять нечего")
    if errors:
        raise ValidationError("; ".join(dict.fromkeys(errors)), code="template.invalid")
    return TemplateInput(title, description, body, tuple(fields), data.file_id)


async def _file_lines(session: AsyncSession, user_id: int, file_id: int | None) -> list[str] | None:
    if file_id is None:
        return None
    repo = TemplateFileRepository(session)
    file = await repo.get(user_id, file_id)
    if file is None:
        raise NotFoundError(
            "Файл-образец не найден, загрузите его снова", code="template.file_not_found"
        )
    return (await repo.text(file.id) or "").split("\n")


def _new_slug() -> str:
    return f"my-{secrets.token_hex(5)}"


async def _own(repo: TemplateRepository, user_id: int, template_id: int) -> Template:
    template = _visible(await repo.get(template_id), user_id)
    if template.owner_user_id is None:
        raise ForbiddenError(
            "Стандартный шаблон не меняется — сохраните свой на его основе",
            code="template.builtin",
        )
    return template


async def create_template(
    session: AsyncSession, *, user_id: int, data: TemplateInput
) -> TemplateView:
    clean = _clean(data, await _file_lines(session, user_id, data.file_id))
    repo = TemplateRepository(session)
    if await repo.count_owned(user_id) >= OWN_TEMPLATES_MAX:
        raise ValidationError(
            f"Своих шаблонов уже {OWN_TEMPLATES_MAX} — удалите ненужные",
            code="template.limit",
        )
    template = await repo.create(
        owner_user_id=user_id,
        slug=_new_slug(),
        title=clean.title,
        kind=CUSTOM_KIND,
        description=clean.description,
        fields=_specs_to_json(clean.fields),
        body=clean.body,
        body_format=DOCX_FORMAT if clean.file_id is not None else TEXT_FORMAT,
        file_id=clean.file_id,
    )
    return to_view(template)


async def update_template(
    session: AsyncSession, *, user_id: int, template_id: int, data: TemplateInput
) -> TemplateView:
    """Правка своего шаблона. Id и слуг остаются прежними — ссылки и кнопки в
    чате ведут на новую редакцию. Документы на шаблоне держат прошлую: иначе
    отправленный счёт молча поменял бы текст, а поля, которых больше нет,
    стали бы в нём ошибками."""
    repo = TemplateRepository(session)
    template = await _own(repo, user_id, template_id)
    clean = _clean(data, await _file_lines(session, user_id, data.file_id))
    if await repo.is_used(template.id):
        previous = await repo.create(
            owner_user_id=user_id,
            slug=_new_slug(),
            title=template.title,
            kind=template.kind,
            description=template.description,
            fields=list(template.fields),
            body=template.body,
            body_format=template.body_format,
            archived_at=datetime.now(UTC),
            origin_id=template.id,
            file_id=template.file_id,
        )
        await repo.move_documents(template.id, previous.id)
    template.title = clean.title
    template.description = clean.description
    template.fields = _specs_to_json(clean.fields)
    template.body = clean.body
    template.body_format = DOCX_FORMAT if clean.file_id is not None else TEXT_FORMAT
    template.file_id = clean.file_id
    await session.flush()
    await session.refresh(template, ["file"])
    return to_view(template)


async def delete_template(session: AsyncSession, *, user_id: int, template_id: int) -> None:
    """Шаблон без документов удаляется, с документами — скрывается из
    библиотеки: документы на нём по-прежнему открываются и собираются."""
    repo = TemplateRepository(session)
    template = await _own(repo, user_id, template_id)
    if await repo.is_used(template.id):
        template.archived_at = datetime.now(UTC)
        await session.flush()
    else:
        await repo.delete(template)
