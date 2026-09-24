"""Журнал фактов: путь документа от создания до доставки, история, копия, активность."""

from __future__ import annotations

from datetime import UTC, datetime

from fakeredis import aioredis as fakeredis_aio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DocumentEvent, UserActivityDay
from core.db.repositories import DownloadTokenRepository, UserRepository
from core.domain.documents import FieldValue, ValueSource
from core.events import EventBus
from core.files import FilesConfig
from core.usecases.documents import (
    DOCX,
    Fact,
    confirm_fields,
    copy_document,
    create_draft,
    document_history,
    ensure_builtin_templates,
    list_documents,
    list_templates,
    record_delivery,
    render_document,
    save_company_profile,
    send_document_to_chat,
    set_fields,
)
from core.usecases.users import mark_active
from tests.usecases.test_document_files import READY_OFFER, _ready_document
from tests.usecases.test_documents import make_user


async def _kinds(session: AsyncSession, document_id: int) -> list[str]:
    rows = await session.execute(
        select(DocumentEvent.kind)
        .where(DocumentEvent.document_id == document_id)
        .order_by(DocumentEvent.id)
    )
    return list(rows.scalars())


async def test_document_path_is_recorded_from_creation_to_delivery(
    session: AsyncSession, redis: fakeredis_aio.FakeRedis, files_config: FilesConfig
) -> None:
    user_id = await make_user(session, max_user_id=501)
    document_id = await _ready_document(session, user_id)
    await render_document(
        session, user_id=user_id, document_id=document_id, fmt=DOCX, cfg=files_config
    )
    bus = EventBus(redis, stream_to_bot="test:to_bot", source="test", maxlen=100)
    _, event_id = await send_document_to_chat(
        session,
        user_id=user_id,
        max_user_id=501,
        document_id=document_id,
        fmt=DOCX,
        cfg=files_config,
        bus=bus,
        tokens=DownloadTokenRepository(redis),
    )

    assert await record_delivery(
        session,
        max_user_id=501,
        document_id=document_id,
        event_id=event_id,
        fmt=DOCX,
        delivered=True,
    )
    assert await record_delivery(
        session,
        max_user_id=501,
        document_id=document_id,
        event_id=event_id,
        fmt=DOCX,
        delivered=True,
    ), "повтор отчёта не пишет второй факт"

    history = await document_history(session, user_id=user_id, document_id=document_id)
    assert [fact.kind for fact in history] == [
        Fact.CREATED,
        Fact.READY,
        Fact.RENDERED,
        Fact.SENT,
        Fact.DELIVERED,
    ]
    rendered = history[2]
    assert rendered.format == DOCX
    (summary,) = await list_documents(session, user_id=user_id)
    assert summary.client == "ООО «Клиент»"
    assert summary.sent is not None
    assert (summary.sent.format, summary.sent.delivery) == (DOCX, "delivered")


async def test_foreign_or_unknown_delivery_reports_are_ignored(
    session: AsyncSession, redis: fakeredis_aio.FakeRedis, files_config: FilesConfig
) -> None:
    owner = await make_user(session, max_user_id=601)
    await make_user(session, max_user_id=602)
    document_id = await _ready_document(session, owner)
    _, event_id = await send_document_to_chat(
        session,
        user_id=owner,
        max_user_id=601,
        document_id=document_id,
        fmt=DOCX,
        cfg=files_config,
        bus=EventBus(redis, stream_to_bot="test:to_bot", source="test", maxlen=100),
        tokens=DownloadTokenRepository(redis),
    )

    assert not await record_delivery(
        session,
        max_user_id=602,
        document_id=document_id,
        event_id=event_id,
        fmt=DOCX,
        delivered=True,
    )
    assert not await record_delivery(
        session, max_user_id=601, document_id=document_id, event_id="nope", fmt=DOCX, delivered=True
    )
    assert await record_delivery(
        session,
        max_user_id=601,
        document_id=document_id,
        event_id=event_id,
        fmt=DOCX,
        delivered=False,
        error="max_api.403",
    )
    (summary,) = await list_documents(session, user_id=owner)
    assert summary.sent is not None and summary.sent.delivery == "failed"
    history = await document_history(session, user_id=owner, document_id=document_id)
    assert history[-1].kind == Fact.DELIVERY_FAILED and history[-1].code == "max_api.403"


async def test_rejected_values_and_ready_transitions(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    offer = (await list_templates(session, user_id=user_id, slug="offer"))[0]
    draft = await create_draft(session, user_id=user_id, template_id=offer.id)
    await set_fields(
        session,
        user_id=user_id,
        document_id=draft.id,
        values=READY_OFFER
        | {"seller_email": FieldValue("не почта", ValueSource.AGENT, confirmed=False)},
    )
    await set_fields(
        session, user_id=user_id, document_id=draft.id, values={"total": FieldValue("")}
    )
    await set_fields(
        session, user_id=user_id, document_id=draft.id, values={"total": FieldValue("100")}
    )
    await confirm_fields(session, user_id=user_id, document_id=draft.id)

    history = await document_history(session, user_id=user_id, document_id=draft.id)
    assert [fact.kind for fact in history] == [
        Fact.CREATED,
        Fact.READY,
        Fact.REJECTED,
        Fact.READY,
    ], "готовность пишется на переходе, а не на каждом сохранении"
    rejected = history[2]
    assert (rejected.code, rejected.source) == ("field.email_invalid", "agent")


async def test_rejected_value_does_not_keep_document_in_draft(session: AsyncSession) -> None:
    """Отклонённое значение не сохраняется, значит и статус считается без него."""
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    offer = (await list_templates(session, user_id=user_id, slug="offer"))[0]
    draft = await create_draft(session, user_id=user_id, template_id=offer.id)
    view = await set_fields(
        session,
        user_id=user_id,
        document_id=draft.id,
        values=READY_OFFER | {"seller_email": FieldValue("не почта")},
    )
    assert view.ready and view.status == "ready"
    assert [e.code for e in view.errors] == ["field.email_invalid"]


async def test_copy_takes_terms_but_not_number_and_dates(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    await save_company_profile(
        session, user_id=user_id, name="ООО «Старое»", values={"inn": "7707083893"}
    )
    invoice = (await list_templates(session, user_id=user_id, slug="invoice"))[0]
    source = await create_draft(session, user_id=user_id, template_id=invoice.id, title="Счёт №7")
    await set_fields(
        session,
        user_id=user_id,
        document_id=source.id,
        values={
            "number": FieldValue("7"),
            "date": FieldValue("24.09.2026"),
            "item": FieldValue("Сопровождение сайта"),
            "total": FieldValue("30 000", ValueSource.AGENT, confirmed=False),
        },
    )
    await save_company_profile(
        session, user_id=user_id, name="ООО «Новое»", values={"inn": "7707083893"}
    )

    copy = await copy_document(session, user_id=user_id, document_id=source.id)

    assert copy.id != source.id and copy.title == "Счёт №7"
    assert "number" not in copy.values and "date" not in copy.values
    assert copy.values["item"].value == "Сопровождение сайта"
    assert copy.values["total"].confirmed is False, "непроверенное остаётся непроверенным"
    assert copy.values["seller_name"].value == "ООО «Новое»", "реквизиты — из свежего профиля"
    history = await document_history(session, user_id=user_id, document_id=copy.id)
    assert [(f.kind, f.source) for f in history] == [(Fact.CREATED, "copy")]


async def test_activity_is_one_row_per_user_and_day(session: AsyncSession) -> None:
    user_id = await make_user(session)
    morning = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    await mark_active(session, user_id, now=morning)
    await mark_active(session, user_id, now=morning.replace(hour=12))
    # 22:30 UTC — уже следующий день по Москве.
    await mark_active(session, user_id, now=morning.replace(hour=22, minute=30))
    days = (
        await session.execute(select(UserActivityDay.day).order_by(UserActivityDay.day))
    ).scalars()
    assert [d.isoformat() for d in days] == ["2026-09-24", "2026-09-25"]
    assert await UserRepository(session).get_by_id(user_id) is not None
