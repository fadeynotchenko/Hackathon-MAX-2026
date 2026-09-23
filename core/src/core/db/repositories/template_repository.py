"""Шаблоны документов: встроенные (без владельца) и загруженные компанией."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Template


class TemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, template_id: int) -> Template | None:
        return await self._session.get(Template, template_id)

    async def get_by_slug(self, slug: str) -> Template | None:
        result = await self._session.execute(select(Template).where(Template.slug == slug))
        return result.scalar_one_or_none()

    async def list_available(self, user_id: int, *, slug: str | None = None) -> list[Template]:
        """Системные шаблоны плюс свои: чужие не видны даже по прямому id."""
        stmt = (
            select(Template)
            .where(or_(Template.owner_user_id.is_(None), Template.owner_user_id == user_id))
            .order_by(Template.owner_user_id.is_(None).desc(), Template.title)
        )
        if slug is not None:
            stmt = stmt.where(Template.slug == slug)
        return list((await self._session.execute(stmt)).scalars())

    async def upsert_builtin(
        self,
        *,
        slug: str,
        title: str,
        kind: str,
        description: str,
        fields: list[dict[str, object]],
        body: str,
        body_format: str,
    ) -> Template:
        template = await self.get_by_slug(slug)
        if template is None:
            template = Template(slug=slug, owner_user_id=None)
            self._session.add(template)
        template.title = title
        template.kind = kind
        template.description = description
        template.fields = fields
        template.body = body
        template.body_format = body_format
        await self._session.flush()
        return template
