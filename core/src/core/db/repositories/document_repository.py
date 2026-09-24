"""Документы пользователя. Шаблон подгружается сразу: без него нечего показывать."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.db.models import Document


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

    async def list_for_user(self, user_id: int, *, limit: int = 50) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.user_id == user_id)
            .options(selectinload(Document.template), selectinload(Document.counterparty))
            .order_by(Document.updated_at.desc(), Document.id.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def create(
        self,
        user_id: int,
        *,
        template_id: int,
        counterparty_id: int | None,
        title: str,
        values: dict[str, dict[str, object]],
    ) -> Document:
        document = Document(
            user_id=user_id,
            template_id=template_id,
            counterparty_id=counterparty_id,
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
