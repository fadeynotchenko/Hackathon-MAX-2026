"""Каталог шаблонов: встроенные заводятся при старте, свои пишет пользователь.

Свой шаблон устроен как встроенный — текст с маркерами ``{{key}}`` и описание
полей, — поэтому заполнение, проверка, помощник и сборка файла работают с ним
без отдельной ветки. Реквизиты сторон узнаются по ключу (``seller_inn``,
``client_name``) и подставляются из организации и карточки клиента.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Template
from core.db.repositories import TemplateRepository
from core.domain.documents import FieldSpec, FieldType, fill_text_template, template_markers
from core.domain.exceptions import ForbiddenError, NotFoundError, ValidationError
from core.usecases.documents.builtin import BUILTIN_TEMPLATES, CLIENT, SELLER, SUBJECT
from core.usecases.documents.requisites import CLIENT_PREFIX, REQUISITE_FIELDS, SELLER_PREFIX

# Вид своего шаблона: в метриках свои шаблоны считаются отдельно от счетов и КП.
CUSTOM_KIND = "custom"
# Название шаблона становится текстом кнопки в чате бота, а там предел — 64 символа.
TITLE_MAX = 64
DESCRIPTION_MAX = 300
BODY_MAX = 20_000
LABEL_MAX = 100
HINT_MAX = 200
FIELDS_MAX = 50
# Каталог и кнопки выбора в чате должны оставаться обозримыми.
OWN_TEMPLATES_MAX = 50
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_REQUISITE_TYPES = {spec.key: spec.type for spec in REQUISITE_FIELDS}


@dataclass(frozen=True)
class TemplateView:
    id: int
    slug: str
    title: str
    kind: str
    description: str
    body_format: str
    is_builtin: bool
    fields: tuple[FieldSpec, ...]
    body: str

    @property
    def preview(self) -> str:
        """Пустой бланк: так документ выглядит до первого заполненного поля."""
        return fill_text_template(self.body, {})


@dataclass(frozen=True)
class TemplateInput:
    """Свой шаблон, как его прислал клиент. Раздел поля и тип реквизита
    сервер определяет сам по ключу."""

    title: str
    description: str
    body: str
    fields: tuple[FieldSpec, ...]


def _specs_from_json(raw: list[dict[str, object]]) -> tuple[FieldSpec, ...]:
    return tuple(
        FieldSpec(
            key=str(item["key"]),
            label=str(item["label"]),
            type=FieldType(str(item.get("type", FieldType.TEXT))),
            required=bool(item.get("required", True)),
            group=str(item.get("group", "")),
            hint=str(item.get("hint", "")),
            max_length=int(item["max_length"]) if item.get("max_length") is not None else None,
            carry_over=bool(item.get("carry_over", True)),
            today_by_default=bool(item.get("today_by_default", False)),
        )
        for item in raw
    )


def _specs_to_json(specs: Iterable[FieldSpec]) -> list[dict[str, object]]:
    return [asdict(spec) | {"type": spec.type.value} for spec in specs]


def to_view(template: Template) -> TemplateView:
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
            body_format="text",
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
    template = await TemplateRepository(session).get(template_id)
    return to_view(_visible(template, user_id))


async def latest_template(session: AsyncSession, template: Template) -> TemplateView:
    """Шаблон для копии документа: прошлая редакция отсылает к живому шаблону,
    чтобы «на основе этого» брало исправленный текст. Удалённый шаблон копия
    не воскрешает в библиотеке, но и не ломается: остаётся текст документа."""
    if template.origin_id is not None:
        origin = await TemplateRepository(session).get(template.origin_id)
        if origin is not None and origin.archived_at is None:
            return to_view(origin)
    return to_view(template)


def _group(key: str) -> str:
    if key.startswith(SELLER_PREFIX):
        return SELLER
    if key.startswith(CLIENT_PREFIX):
        return CLIENT
    return SUBJECT


def _requisite_type(key: str) -> FieldType | None:
    """Реквизит стороны проверяется по своему типу, что бы ни прислал клиент:
    иначе «ИНН клиента» текстовым полем обходил бы контрольную сумму."""
    for prefix in (SELLER_PREFIX, CLIENT_PREFIX):
        if key.startswith(prefix):
            return _REQUISITE_TYPES.get(key.removeprefix(prefix))
    return None


def _marker(key: str) -> str:
    return "{{" + key + "}}"


def _clean(data: TemplateInput) -> TemplateInput:
    """Проверить шаблон целиком и собрать все замечания в одно сообщение:
    человек правит текст на телефоне, и ошибки по одной стоили бы ему кругов."""
    errors: list[str] = []
    title = data.title.strip()
    if not title:
        errors.append("Назовите шаблон")
    elif len(title) > TITLE_MAX:
        errors.append(f"Название шаблона — не длиннее {TITLE_MAX} символов")
    description = data.description.strip()
    if len(description) > DESCRIPTION_MAX:
        errors.append(f"Описание — не длиннее {DESCRIPTION_MAX} символов")
    body = data.body.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not body:
        errors.append("Напишите текст шаблона")
    elif len(body) > BODY_MAX:
        errors.append(f"Текст шаблона — не длиннее {BODY_MAX} символов")
    if len(data.fields) > FIELDS_MAX:
        errors.append(f"Полей в шаблоне — не больше {FIELDS_MAX}")

    fields: list[FieldSpec] = []
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
            field_type = _requisite_type(spec.key) or spec.type
            fields.append(
                FieldSpec(
                    key=spec.key,
                    label=label,
                    type=field_type,
                    required=spec.required,
                    group=_group(spec.key),
                    hint=spec.hint.strip()[:HINT_MAX],
                    carry_over=spec.carry_over,
                    today_by_default=spec.today_by_default and field_type is FieldType.DATE,
                )
            )

    used = template_markers(body)
    declared = {spec.key for spec in data.fields}
    errors.extend(
        f"В тексте есть поле {_marker(key)}, которого нет в списке полей"
        for key in used
        if key not in declared
    )
    errors.extend(
        f"Поле «{field.label}» не встречается в тексте" for field in fields if field.key not in used
    )
    if body and not used:
        errors.append("Добавьте в текст хотя бы одно поле — иначе заполнять нечего")
    if errors:
        raise ValidationError("; ".join(dict.fromkeys(errors)), code="template.invalid")
    return TemplateInput(title, description, body, tuple(fields))


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
    clean = _clean(data)
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
        body_format="text",
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
    clean = _clean(data)
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
        )
        await repo.move_documents(template.id, previous.id)
    template.title = clean.title
    template.description = clean.description
    template.fields = _specs_to_json(clean.fields)
    template.body = clean.body
    await session.flush()
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
