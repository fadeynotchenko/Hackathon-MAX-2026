"""Метрики для админ-панели на заранее разложенных фактах: дни по Москве, воронка,
доля автозаполнения, пойманные ошибки, доставки, время до отправки и сборки."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import (
    ActivityRepository,
    DocumentEventRepository,
    DocumentRepository,
    UserRepository,
    UserUpsert,
)
from core.usecases.admin import admin_metrics
from core.usecases.admin.metrics import percentile
from core.usecases.documents import ensure_builtin_templates, list_templates

TODAY = date(2026, 9, 24)


def _at(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, second, tzinfo=UTC)


async def _user(session: AsyncSession, max_user_id: int, created_at: datetime) -> int:
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(max_user_id=max_user_id, first_name="U"), touch_login=False, now=created_at
    )
    user.created_at = created_at
    await session.flush()
    return user.id


async def _document(
    session: AsyncSession, user_id: int, template_id: int, created_at: datetime, sources: dict
) -> int:
    document = await DocumentRepository(session).create(
        user_id,
        template_id=template_id,
        counterparty_id=None,
        title="Документ",
        values={key: {"value": "x", "source": source} for key, source in sources.items()},
    )
    document.created_at = created_at
    await session.flush()
    return document.id


async def test_metrics_are_built_from_facts_by_moscow_days(session: AsyncSession) -> None:
    u1 = await _user(session, 1, datetime(2026, 9, 10, tzinfo=UTC))
    u2 = await _user(session, 2, _at(20, 10))
    u3 = await _user(session, 3, _at(23, 22, 30))  # по Москве уже 24-е
    activity = ActivityRepository(session)
    for user_id, day in [(u1, 12), (u1, 18), (u1, 24), (u2, 20), (u2, 21), (u3, 24)]:
        await activity.touch(user_id, date(2026, 9, day))

    await ensure_builtin_templates(session)
    templates = {t.kind: t.id for t in await list_templates(session, user_id=u1)}
    doc_a = await _document(
        session,
        u1,
        templates["invoice"],
        _at(20, 12),
        {
            "number": "manual",
            "date": "manual",
            "seller_name": "profile",
            "seller_inn": "profile",
            "client_name": "counterparty",
            "total": "agent",
        },
    )
    doc_b = await _document(
        session, u2, templates["offer"], _at(22, 9), {"client_inn": "ocr", "total": "manual"}
    )
    doc_c = await _document(session, u3, templates["contract"], _at(23, 22, 30), {})
    doc_d = await _document(
        session, u1, templates["invoice"], datetime(2026, 9, 10, tzinfo=UTC), {"x": "manual"}
    )
    journal = DocumentEventRepository(session)
    facts = [
        (u1, doc_a, "created", {"template_kind": "invoice"}, _at(20, 12)),
        (u1, doc_a, "ready", {}, _at(20, 12, 5)),
        (u1, doc_a, "rendered", {"fmt": "pdf", "duration_ms": 1500}, _at(20, 12, 6)),
        (u1, doc_a, "sent", {"fmt": "pdf", "event_id": "e1"}, _at(20, 12, 10)),
        (u1, doc_a, "delivered", {"fmt": "pdf", "event_id": "e1"}, _at(20, 12, 10, 30)),
        (u2, doc_b, "created", {"template_kind": "offer", "source": "copy"}, _at(22, 9)),
        (u2, doc_b, "rejected", {"code": "field.inn_invalid", "source": "manual"}, _at(22, 9, 1)),
        (u2, doc_b, "rejected", {"code": "field.inn_invalid", "source": "ocr"}, _at(22, 9, 2)),
        (u2, doc_b, "ready", {}, _at(22, 9, 10)),
        (u2, doc_b, "rendered", {"fmt": "docx", "duration_ms": 200}, _at(22, 9, 11)),
        (u2, doc_b, "sent", {"fmt": "docx", "event_id": "e2"}, _at(22, 9, 30)),
        (u3, doc_c, "created", {"template_kind": "contract"}, _at(23, 22, 30)),
        (u3, doc_c, "rejected", {"code": "field.bic_invalid", "source": "manual"}, _at(24, 8)),
        (u1, doc_d, "created", {"template_kind": "invoice"}, datetime(2026, 9, 10, tzinfo=UTC)),
        (u1, doc_d, "sent", {"fmt": "docx", "event_id": "e3"}, _at(19, 0)),
        (u1, doc_d, "delivery_failed", {"code": "max_api.403", "event_id": "e3"}, _at(19, 0, 1)),
    ]
    for user_id, document_id, kind, extra, at in facts:
        await journal.add(user_id=user_id, kind=kind, document_id=document_id, at=at, **extra)

    metrics = await admin_metrics(session, days=7, today=TODAY)

    assert (metrics.since, metrics.until) == (date(2026, 9, 18), TODAY)
    days = {d.day.day: d for d in metrics.daily}
    assert list(days) == [18, 19, 20, 21, 22, 23, 24]
    assert [days[d].users_total for d in (18, 20, 24)] == [1, 2, 3]
    assert (days[20].users_new, days[24].users_new, days[23].users_new) == (1, 1, 0)
    assert (days[24].active_day, days[24].active_week) == (2, 3)
    assert days[18].active_week == 1, "неделя 12–18 сентября: только первый пользователь"
    assert days[20].created_by_kind == {"invoice": 1}
    assert (days[20].rendered_pdf, days[20].sent, days[20].delivered) == (1, 1, 1)
    assert (days[22].documents_copied, days[22].rejected, days[22].rendered_docx) == (1, 2, 1)
    assert (days[19].sent, days[19].delivery_failed) == (1, 1)
    assert days[24].created_by_kind == {"contract": 1} and days[23].documents_created == 0

    funnel = metrics.funnel
    assert (funnel.created, funnel.ready, funnel.rendered, funnel.sent, funnel.delivered) == (
        3,
        2,
        2,
        2,
        1,
    )
    assert metrics.autofill.by_source == {
        "manual": 3,
        "profile": 2,
        "counterparty": 1,
        "ocr": 1,
        "agent": 1,
        "default": 0,
    }
    assert metrics.autofill.total == 8 and metrics.autofill.automatic_share == 0.625
    assert metrics.rejections == {"field.inn_invalid": 2, "field.bic_invalid": 1}
    deliveries = metrics.deliveries
    assert (deliveries.delivered, deliveries.failed, deliveries.pending) == (1, 1, 1)
    send = metrics.time_to_send_minutes
    assert (send.count, send.median, send.p90) == (3, 30.0, 12960.0)
    assert metrics.render_ms["pdf"].median == 1500 and metrics.render_ms["docx"].count == 1


async def test_empty_period_has_zeros_not_errors(session: AsyncSession) -> None:
    metrics = await admin_metrics(session, days=3, today=TODAY)
    assert [d.day.day for d in metrics.daily] == [22, 23, 24]
    assert all(d.users_total == 0 and d.documents_created == 0 for d in metrics.daily)
    assert metrics.autofill.automatic_share is None
    assert metrics.time_to_send_minutes.median is None
    assert metrics.funnel.created == 0 and metrics.render_ms == {}


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([], 0.9) is None
    assert percentile([5], 0.9) == 5
    assert percentile(list(range(1, 11)), 0.9) == 9
    assert percentile([3, 1, 2], 0.5) == 2
