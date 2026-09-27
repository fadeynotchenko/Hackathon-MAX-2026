"""Шаблоны документов: встроенные (без владельца), свои шаблоны пользователя
и их файлы-образцы."""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Document, Template, TemplateFile


class TemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, template_id: int) -> Template | None:
        return await self._session.get(Template, template_id)

    async def get_by_slug(self, slug: str) -> Template | None:
        result = await self._session.execute(select(Template).where(Template.slug == slug))
        return result.scalar_one_or_none()

    async def list_available(self, user_id: int, *, slug: str | None = None) -> list[Template]:
        """Системные шаблоны плюс свои: чужие не видны даже по прямому id,
        удалённые и прошлые редакции своих — тоже."""
        stmt = (
            select(Template)
            .where(
                or_(Template.owner_user_id.is_(None), Template.owner_user_id == user_id),
                Template.archived_at.is_(None),
            )
            .order_by(Template.owner_user_id.is_(None).desc(), Template.title)
        )
        if slug is not None:
            stmt = stmt.where(Template.slug == slug)
        return list((await self._session.execute(stmt)).scalars())

    async def count_owned(self, user_id: int) -> int:
        stmt = select(func.count(Template.id)).where(
            Template.owner_user_id == user_id, Template.archived_at.is_(None)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def is_used(self, template_id: int) -> bool:
        stmt = select(exists().where(Document.template_id == template_id))
        return bool((await self._session.execute(stmt)).scalar_one())

    async def create(
        self,
        *,
        owner_user_id: int | None,
        slug: str,
        title: str,
        kind: str,
        description: str,
        fields: list[dict[str, object]],
        body: str,
        body_format: str,
        archived_at: datetime | None = None,
        origin_id: int | None = None,
        file_id: int | None = None,
    ) -> Template:
        template = Template(
            owner_user_id=owner_user_id,
            slug=slug,
            title=title,
            kind=kind,
            description=description,
            fields=fields,
            body=body,
            body_format=body_format,
            archived_at=archived_at,
            origin_id=origin_id,
            file_id=file_id,
        )
        self._session.add(template)
        await self._session.flush()
        await self._session.refresh(template, ["file"])
        return template

    async def move_documents(self, from_id: int, to_id: int) -> None:
        """Документы прошлой редакции переезжают на её архивную копию."""
        await self._session.execute(
            update(Document).where(Document.template_id == from_id).values(template_id=to_id)
        )

    async def delete(self, template: Template) -> None:
        await self._session.delete(template)
        await self._session.flush()

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


class TemplateFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, owner_user_id: int, filename: str, data: bytes, text: str
    ) -> TemplateFile:
        file = TemplateFile(
            owner_user_id=owner_user_id,
            filename=filename,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            data=data,
            text=text,
        )
        self._session.add(file)
        await self._session.flush()
        return file

    async def get(self, owner_user_id: int, file_id: int) -> TemplateFile | None:
        stmt = select(TemplateFile).where(
            TemplateFile.id == file_id, TemplateFile.owner_user_id == owner_user_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def data(self, file_id: int) -> bytes | None:
        stmt = select(TemplateFile.data).where(TemplateFile.id == file_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def text(self, file_id: int) -> str | None:
        stmt = select(TemplateFile.text).where(TemplateFile.id == file_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def delete_unused(self, owner_user_id: int, *, before: datetime) -> None:
        """Загруженные, но так и не сохранённые шаблоном образцы: пользователь
        выбрал другой файл или ушёл с экрана."""
        used = select(Template.file_id).where(Template.file_id.is_not(None))
        await self._session.execute(
            delete(TemplateFile).where(
                TemplateFile.owner_user_id == owner_user_id,
                TemplateFile.created_at < before,
                TemplateFile.id.not_in(used),
            )
        )
