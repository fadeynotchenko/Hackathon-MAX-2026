"""Каталог шаблонов: встроенные заводятся при старте, наружу уходят как dataclass."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Template
from core.db.repositories import TemplateRepository
from core.domain.documents import FieldSpec, FieldType
from core.domain.exceptions import NotFoundError
from core.usecases.documents.builtin import BUILTIN_TEMPLATES


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
            fields=[asdict(spec) | {"type": spec.type.value} for spec in template.fields],
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


async def get_template(session: AsyncSession, *, user_id: int, template_id: int) -> TemplateView:
    template = await TemplateRepository(session).get(template_id)
    if template is None or (
        template.owner_user_id is not None and template.owner_user_id != user_id
    ):
        raise NotFoundError("Шаблон не найден", code="template.not_found")
    return to_view(template)
