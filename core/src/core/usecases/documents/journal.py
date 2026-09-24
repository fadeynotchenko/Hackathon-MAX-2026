"""Журнал фактов по документам: то, что проходит через систему и нужно истории и метрикам.

Факт пишется в той же транзакции, что и действие: «отправлен» без события боту
или событие без записи невозможны. Доставку подтверждает бот отдельным
событием; её факт сшивается с отправкой по UUID события ``document.ready``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DocumentEvent
from core.db.repositories import DocumentEventRepository, DocumentRepository, UserRepository
from core.domain.exceptions import NotFoundError
from core.logs import biz_warn

logger = logging.getLogger(__name__)


class Fact(StrEnum):
    CREATED = "created"
    READY = "ready"
    RENDERED = "rendered"
    SENT = "sent"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    REJECTED = "rejected"


# Источник у факта «создан»: документ взят за основу другого.
COPY_SOURCE = "copy"
DELIVERY_PENDING = "pending"
DELIVERY_DELIVERED = "delivered"
DELIVERY_FAILED = "failed"


@dataclass(frozen=True)
class DocumentFact:
    kind: str
    format: str | None
    code: str | None
    source: str | None
    at: datetime


@dataclass(frozen=True)
class SendState:
    """Последняя отправка документа в чат и чем она закончилась."""

    sent_at: datetime
    format: str | None
    delivery: str


async def record(
    session: AsyncSession,
    *,
    user_id: int,
    kind: Fact,
    document_id: int | None = None,
    template_kind: str | None = None,
    fmt: str | None = None,
    code: str | None = None,
    source: str | None = None,
    event_id: str | None = None,
    duration_ms: int | None = None,
) -> None:
    await DocumentEventRepository(session).add(
        user_id=user_id,
        kind=kind.value,
        document_id=document_id,
        template_kind=template_kind,
        fmt=fmt,
        code=code,
        source=source,
        event_id=event_id,
        duration_ms=duration_ms,
    )


def _fact(row: DocumentEvent) -> DocumentFact:
    return DocumentFact(row.kind, row.format, row.code, row.source, row.created_at)


async def document_history(
    session: AsyncSession, *, user_id: int, document_id: int
) -> list[DocumentFact]:
    if await DocumentRepository(session).get(user_id, document_id) is None:
        raise NotFoundError("Документ не найден", code="document.not_found")
    rows = await DocumentEventRepository(session).list_for_document(user_id, document_id)
    return [_fact(row) for row in rows]


async def last_sends(session: AsyncSession, document_ids: Sequence[int]) -> dict[int, SendState]:
    rows = await DocumentEventRepository(session).for_documents(
        document_ids, {Fact.SENT, Fact.DELIVERED, Fact.DELIVERY_FAILED}
    )
    outcomes: dict[str, str] = {}
    sends: dict[int, DocumentEvent] = {}
    for row in rows:
        if row.kind == Fact.SENT and row.document_id is not None:
            sends[row.document_id] = row
        elif row.event_id:
            outcomes[row.event_id] = (
                DELIVERY_DELIVERED if row.kind == Fact.DELIVERED else DELIVERY_FAILED
            )
    return {
        document_id: SendState(
            sent_at=row.created_at,
            format=row.format,
            delivery=outcomes.get(row.event_id or "", DELIVERY_PENDING),
        )
        for document_id, row in sends.items()
    }


async def record_delivery(
    session: AsyncSession,
    *,
    max_user_id: int,
    document_id: int,
    event_id: str,
    fmt: str,
    delivered: bool,
    error: str | None = None,
) -> bool:
    """Бот сообщил, чем закончилась доставка файла. Факт пишется только к известной
    отправке того же пользователя: чужой или выдуманный UUID журнал не пополняет."""
    events = DocumentEventRepository(session)
    sent = await events.find(event_id, Fact.SENT)
    user = await UserRepository(session).get_by_max_id(max_user_id)
    matches = (
        sent is not None
        and user is not None
        and sent.user_id == user.id
        and sent.document_id in (None, document_id)
    )
    if not matches or sent is None or user is None:
        biz_warn(
            logger,
            "documents.delivery.unknown",
            event_id=event_id,
            document_id=document_id,
            max_user_id=max_user_id,
        )
        return False
    kind = Fact.DELIVERED if delivered else Fact.DELIVERY_FAILED
    if await events.find(event_id, kind) is not None:
        return True
    await record(
        session,
        user_id=user.id,
        kind=kind,
        document_id=sent.document_id,
        template_kind=sent.template_kind,
        fmt=fmt,
        code=None if delivered else (error or "unknown"),
        event_id=event_id,
    )
    return True
