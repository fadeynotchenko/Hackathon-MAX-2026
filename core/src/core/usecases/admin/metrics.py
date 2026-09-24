"""Метрики для владельца продукта: графики по дням за период (пункт 17 бэклога).

Всё считается из того, что система уже хранит: пользователи и дни их
активности, журнал фактов по документам, значения полей с источником.
Отдельного хранилища метрик нет — пересчёт окна в полгода укладывается в
несколько запросов, а второй источник правды разошёлся бы с журналом.

«День» — московский (``core.domain.calendar``).
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DocumentEvent
from core.db.repositories import (
    ActivityRepository,
    DocumentEventRepository,
    DocumentRepository,
    UserRepository,
)
from core.domain.calendar import day_start, local_day
from core.domain.documents import ValueSource
from core.usecases.documents.journal import COPY_SOURCE, Fact

MAX_DAYS = 180
WEEK = 7
_DAY = timedelta(days=1)


@dataclass(frozen=True)
class DailyMetrics:
    day: date
    users_total: int
    users_new: int
    active_day: int
    # Уникальные активные за семь дней, закончившихся этим днём.
    active_week: int
    documents_created: int
    documents_copied: int
    created_by_kind: dict[str, int]
    rendered_docx: int
    rendered_pdf: int
    sent: int
    delivered: int
    delivery_failed: int
    rejected: int


@dataclass(frozen=True)
class Funnel:
    """Документы, созданные в периоде, и сколько из них дошло до каждого шага."""

    created: int
    ready: int
    rendered: int
    sent: int
    delivered: int


@dataclass(frozen=True)
class Autofill:
    """Поля документов периода по источнику значения: сколько работы снял продукт."""

    by_source: dict[str, int]
    total: int
    automatic_share: float | None


@dataclass(frozen=True)
class Distribution:
    count: int
    median: float | None
    p90: float | None


@dataclass(frozen=True)
class Deliveries:
    delivered: int
    failed: int
    pending: int


@dataclass(frozen=True)
class AdminMetrics:
    since: date
    until: date
    daily: tuple[DailyMetrics, ...]
    funnel: Funnel
    autofill: Autofill
    rejections: dict[str, int]
    deliveries: Deliveries
    time_to_send_minutes: Distribution
    render_ms: dict[str, Distribution]


def percentile(values: Sequence[float], share: float) -> float | None:
    """Ближайший ранг: p90 из десяти значений — девятое по возрастанию."""
    if not values:
        return None
    ordered = sorted(values)
    return float(ordered[max(math.ceil(share * len(ordered)), 1) - 1])


def _distribution(values: Sequence[float], *, digits: int = 1) -> Distribution:
    if not values:
        return Distribution(0, None, None)
    p90 = percentile(values, 0.9)
    return Distribution(
        count=len(values),
        median=round(statistics.median(values), digits),
        p90=round(p90, digits) if p90 is not None else None,
    )


def _funnel(cohort: set[int], stages: list[DocumentEvent]) -> Funnel:
    reached: dict[str, set[int]] = defaultdict(set)
    for fact in stages:
        if fact.document_id in cohort:
            reached[fact.kind].add(fact.document_id)
    return Funnel(
        created=len(cohort),
        ready=len(reached[Fact.READY]),
        rendered=len(reached[Fact.RENDERED]),
        sent=len(reached[Fact.SENT]),
        delivered=len(reached[Fact.DELIVERED]),
    )


def _autofill(documents: list[dict[str, dict[str, object]]]) -> Autofill:
    by_source: Counter[str] = Counter({source.value: 0 for source in ValueSource})
    for values in documents:
        for item in values.values():
            by_source[str(item.get("source", ValueSource.MANUAL))] += 1
    total = sum(by_source.values())
    manual = by_source[ValueSource.MANUAL]
    return Autofill(
        by_source=dict(by_source),
        total=total,
        automatic_share=round((total - manual) / total, 3) if total else None,
    )


def _time_to_send(
    history: list[DocumentEvent], window_start: datetime, window_end: datetime
) -> Distribution:
    """От создания документа до первой отправки — для документов, впервые
    отправленных в периоде: повторная отправка старого документа не в счёт."""
    created: dict[int, datetime] = {}
    first_sent: dict[int, datetime] = {}
    for fact in history:
        if fact.document_id is None:
            continue
        target = created if fact.kind == Fact.CREATED else first_sent
        target.setdefault(fact.document_id, fact.created_at)
    minutes = [
        (sent_at - created[document_id]).total_seconds() / 60
        for document_id, sent_at in first_sent.items()
        if document_id in created and window_start <= sent_at < window_end
    ]
    return _distribution(minutes)


async def admin_metrics(
    session: AsyncSession, *, days: int = 30, today: date | None = None
) -> AdminMetrics:
    days = min(max(days, 1), MAX_DAYS)
    until = today or local_day(datetime.now(UTC))
    since = until - (days - 1) * _DAY
    window_start, window_end = day_start(since), day_start(until + _DAY)

    users = UserRepository(session)
    users_before = await users.count_created_before(window_start)
    new_by_day = Counter(
        local_day(moment) for moment in await users.created_between(window_start, window_end)
    )
    active_by_day: dict[date, set[int]] = defaultdict(set)
    for user_id, day in await ActivityRepository(session).between(
        since - (WEEK - 1) * _DAY, until + _DAY
    ):
        active_by_day[day].add(user_id)

    journal = DocumentEventRepository(session)
    facts = await journal.between(window_start, window_end)
    counts: dict[date, Counter[str]] = defaultdict(Counter)
    kinds: dict[date, Counter[str]] = defaultdict(Counter)
    rejections: Counter[str] = Counter()
    render_ms: dict[str, list[float]] = defaultdict(list)
    cohort: set[int] = set()
    sends: list[DocumentEvent] = []
    for fact in facts:
        day = local_day(fact.created_at)
        counts[day][fact.kind] += 1
        if fact.kind == Fact.CREATED:
            kinds[day][fact.template_kind or "other"] += 1
            if fact.source == COPY_SOURCE:
                counts[day]["copied"] += 1
            if fact.document_id is not None:
                cohort.add(fact.document_id)
        elif fact.kind == Fact.RENDERED and fact.format:
            counts[day][f"rendered_{fact.format}"] += 1
            if fact.duration_ms is not None:
                render_ms[fact.format].append(fact.duration_ms)
        elif fact.kind == Fact.REJECTED:
            rejections[fact.code or "unknown"] += 1
        elif fact.kind == Fact.SENT:
            sends.append(fact)

    sent_documents = [fact.document_id for fact in sends if fact.document_id is not None]
    stages = await journal.for_documents(
        sorted(cohort), {Fact.READY, Fact.RENDERED, Fact.SENT, Fact.DELIVERED}
    )
    history = await journal.for_documents(
        sent_documents, {Fact.CREATED, Fact.SENT, Fact.DELIVERED, Fact.DELIVERY_FAILED}
    )
    outcomes = {
        fact.event_id
        for fact in await journal.with_event_ids(
            [fact.event_id for fact in sends if fact.event_id],
            {Fact.DELIVERED, Fact.DELIVERY_FAILED},
        )
    }

    daily: list[DailyMetrics] = []
    total = users_before
    for offset in range(days):
        day = since + offset * _DAY
        total += new_by_day[day]
        week = set().union(*(active_by_day[day - back * _DAY] for back in range(WEEK)))
        daily.append(
            DailyMetrics(
                day=day,
                users_total=total,
                users_new=new_by_day[day],
                active_day=len(active_by_day[day]),
                active_week=len(week),
                documents_created=counts[day][Fact.CREATED],
                documents_copied=counts[day]["copied"],
                created_by_kind=dict(kinds[day]),
                rendered_docx=counts[day]["rendered_docx"],
                rendered_pdf=counts[day]["rendered_pdf"],
                sent=counts[day][Fact.SENT],
                delivered=counts[day][Fact.DELIVERED],
                delivery_failed=counts[day][Fact.DELIVERY_FAILED],
                rejected=counts[day][Fact.REJECTED],
            )
        )

    return AdminMetrics(
        since=since,
        until=until,
        daily=tuple(daily),
        funnel=_funnel(cohort, stages),
        autofill=_autofill(
            await DocumentRepository(session).values_created_between(window_start, window_end)
        ),
        rejections=dict(rejections.most_common()),
        deliveries=Deliveries(
            delivered=sum(c[Fact.DELIVERED] for c in counts.values()),
            failed=sum(c[Fact.DELIVERY_FAILED] for c in counts.values()),
            pending=sum(1 for fact in sends if fact.event_id not in outcomes),
        ),
        time_to_send_minutes=_time_to_send(history, window_start, window_end),
        render_ms={fmt: _distribution(values, digits=0) for fmt, values in render_ms.items()},
    )
