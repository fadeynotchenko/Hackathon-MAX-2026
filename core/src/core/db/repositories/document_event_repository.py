"""Журнал фактов по документам: запись, история документа, выборки для метрик."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DocumentEvent


class DocumentEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        user_id: int,
        kind: str,
        document_id: int | None = None,
        template_kind: str | None = None,
        fmt: str | None = None,
        code: str | None = None,
        source: str | None = None,
        event_id: str | None = None,
        duration_ms: int | None = None,
        at: datetime | None = None,
    ) -> None:
        """Время ставит сервер; ``at`` нужен только тем, кто переносит прошлое (тесты, импорт)."""
        event = DocumentEvent(
            user_id=user_id,
            document_id=document_id,
            kind=kind,
            template_kind=template_kind,
            format=fmt,
            code=code,
            source=source,
            event_id=event_id,
            duration_ms=duration_ms,
        )
        if at is not None:
            event.created_at = at
        self._session.add(event)
        await self._session.flush()

    async def list_for_document(self, user_id: int, document_id: int) -> list[DocumentEvent]:
        stmt = (
            select(DocumentEvent)
            .where(DocumentEvent.user_id == user_id, DocumentEvent.document_id == document_id)
            .order_by(DocumentEvent.created_at, DocumentEvent.id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def for_documents(
        self, document_ids: Sequence[int], kinds: Collection[str]
    ) -> list[DocumentEvent]:
        if not document_ids:
            return []
        stmt = (
            select(DocumentEvent)
            .where(DocumentEvent.document_id.in_(document_ids), DocumentEvent.kind.in_(kinds))
            .order_by(DocumentEvent.created_at, DocumentEvent.id)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def with_event_ids(
        self, event_ids: Sequence[str], kinds: Collection[str]
    ) -> list[DocumentEvent]:
        """Факты по событиям доставки: у удалённого документа document_id пуст,
        а event_id связывает отправку с её исходом и после удаления."""
        if not event_ids:
            return []
        stmt = select(DocumentEvent).where(
            DocumentEvent.event_id.in_(event_ids), DocumentEvent.kind.in_(kinds)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def find(self, event_id: str, kind: str) -> DocumentEvent | None:
        stmt = select(DocumentEvent).where(
            DocumentEvent.event_id == event_id, DocumentEvent.kind == kind
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def between(self, since: datetime, until: datetime) -> list[DocumentEvent]:
        stmt = (
            select(DocumentEvent)
            .where(DocumentEvent.created_at >= since, DocumentEvent.created_at < until)
            .order_by(DocumentEvent.created_at, DocumentEvent.id)
        )
        return list((await self._session.execute(stmt)).scalars())
