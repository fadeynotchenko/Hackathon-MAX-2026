"""Документы пользователя. Шаблон подгружается сразу: без него нечего показывать."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.db.models import Document, Template


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int, document_id: int) -> Document | None:
        stmt = (
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .options(selectinload(Document.template), selectinload(Document.counterparty))
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: int, *, limit: int) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.user_id == user_id)
            .options(selectinload(Document.template), selectinload(Document.counterparty))
            .order_by(Document.updated_at.desc(), Document.id.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def recent_numbers(
        self, user_id: int, *, organization_id: int | None, template_kind: str, limit: int
    ) -> list[str]:
        """Номера последних документов того же вида от той же организации, новые первыми."""
        owner = (
            Document.organization_id.is_(None)
            if organization_id is None
            else Document.organization_id == organization_id
        )
        stmt = (
            select(Document.values)
            .join(Template, Template.id == Document.template_id)
            .where(Document.user_id == user_id, owner, Template.kind == template_kind)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
        )
        numbers: list[str] = []
        for values in (await self._session.execute(stmt)).scalars():
            number = (values or {}).get("number")
            if isinstance(number, dict) and str(number.get("value") or "").strip():
                numbers.append(str(number["value"]).strip())
        return numbers

    async def create(
        self,
        user_id: int,
        *,
        template_id: int,
        counterparty_id: int | None,
        title: str,
        values: dict[str, dict[str, object]],
        organization_id: int | None = None,
    ) -> Document:
        document = Document(
            user_id=user_id,
            template_id=template_id,
            counterparty_id=counterparty_id,
            organization_id=organization_id,
            title=title,
            values=values,
        )
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document, ["template", "counterparty"])
        return document

    async def values_created_between(
        self, since: datetime, until: datetime
    ) -> list[dict[str, dict[str, object]]]:
        """Значения полей документов, созданных в окне: из них считается доля автозаполнения."""
        stmt = select(Document.values).where(
            Document.created_at >= since, Document.created_at < until
        )
        return list((await self._session.execute(stmt)).scalars())

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
        await self._session.flush()

    async def save_values(
        self, document: Document, values: dict[str, dict[str, object]], *, status: str
    ) -> Document:
        document.values = values
        document.status = status
        await self._session.flush()
        # updated_at считает сервер (onupdate), после UPDATE значение в объекте
        # протухает: без явного refresh чтение атрибута ушло бы в ленивый SELECT
        # уже вне greenlet-контекста async-сессии.
        await self._session.refresh(document, ["updated_at"])
        return document
