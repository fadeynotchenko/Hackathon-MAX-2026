"""Календарь продукта: «день» для истории и метрик считается по Москве.

Пользователи и владелец продукта живут по московскому времени, а сервер — в UTC:
документ, отправленный в 01:30 по Москве, относится к новому дню, а не к
вчерашнему. Смещение фиксированное: перехода на летнее время в России нет.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

MSK = timezone(timedelta(hours=3), "MSK")


def local_day(moment: datetime) -> date:
    return moment.astimezone(MSK).date()


def day_start(day: date) -> datetime:
    """Начало московского дня в UTC: граница выборки из базы."""
    return datetime.combine(day, time.min, tzinfo=MSK).astimezone(UTC)
