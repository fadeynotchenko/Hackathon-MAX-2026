"""Шина событий на Redis Streams — шов между Python-ядром и TS-ботом.

Запись стрима (конверт; бот читает и пишет тот же формат в bot/src/events/codec.ts):
    id      — UUID события: ключ идемпотентности потребителя и общий идентификатор в логах
    v       — версия конверта (contracts.ENVELOPE_VERSION)
    type    — имя события из core.events.contracts
    payload — JSON-объект, форма задана моделью из contracts.py
    ts      — ISO-8601 момента публикации
    source  — кто опубликовал: api, bot, имя джобы

Стримы: ``EVENTS_STREAM_TO_BOT`` (ядро → бот) и ``EVENTS_STREAM_TO_CORE`` (бот → ядро).
Потребители читают через consumer group и подтверждают XACK, поэтому событие,
упавшее на временной ошибке, переиграется после рестарта. Окончательные ошибки
(невалидный payload, отказ домена) подтверждаются сразу: повтор их не вылечит.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from core.domain.exceptions import AppError
from core.events.contracts import ENVELOPE_VERSION, NOTIFY_USER, EventPayload, NotifyUser
from core.logs import biz_error, biz_info, biz_warn

logger = logging.getLogger(__name__)

EventHandler = Callable[["Event"], Awaitable[None]]


class EventDecodeError(ValueError):
    """Запись стрима не разбирается как конверт события."""


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any]
    source: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    v: int = ENVELOPE_VERSION
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))
    stream_id: str | None = None

    def to_fields(self) -> dict[str, str]:
        return {
            "id": self.id,
            "v": str(self.v),
            "type": self.type,
            "payload": json.dumps(self.payload, ensure_ascii=False, separators=(",", ":")),
            "ts": self.ts,
            "source": self.source,
        }

    @classmethod
    def from_fields(cls, stream_id: str, fields: dict[str, str]) -> Event:
        """Fail-fast: битая запись — EventDecodeError, а не молчаливый суррогат."""
        event_type = fields.get("type")
        if not event_type:
            raise EventDecodeError(f"запись {stream_id} без поля type")
        try:
            payload = json.loads(fields.get("payload") or "{}")
        except json.JSONDecodeError as exc:
            raise EventDecodeError(f"запись {stream_id}: payload не JSON") from exc
        if not isinstance(payload, dict):
            raise EventDecodeError(f"запись {stream_id}: payload не объект")
        try:
            version = int(fields.get("v") or ENVELOPE_VERSION)
        except ValueError as exc:
            raise EventDecodeError(f"запись {stream_id}: версия не число") from exc
        return cls(
            type=event_type,
            payload=payload,
            source=fields.get("source", ""),
            id=fields.get("id") or stream_id,
            v=version,
            ts=fields.get("ts", ""),
            stream_id=stream_id,
        )


async def publish_event(
    redis: Redis,
    stream: str,
    event_type: str,
    payload: EventPayload | dict[str, Any],
    *,
    source: str,
    maxlen: int,
) -> Event:
    """XADD с приблизительным MAXLEN (стрим не растёт бесконечно). Возвращает событие
    с заполненным ``stream_id``; наружу (API, логи) уходит ``event.id``."""
    data = payload.model_dump() if isinstance(payload, EventPayload) else payload
    event = Event(type=event_type, payload=data, source=source)
    stream_id = str(await redis.xadd(stream, event.to_fields(), maxlen=maxlen, approximate=True))
    biz_info(
        logger,
        "events.published",
        stream=stream,
        type=event_type,
        event_id=event.id,
        stream_id=stream_id,
    )
    return replace(event, stream_id=stream_id)


class EventBus:
    """Публикация в стрим «ядро → бот» с зафиксированным источником (DI в API и джобы)."""

    def __init__(self, redis: Redis, *, stream_to_bot: str, source: str, maxlen: int) -> None:
        self._redis = redis
        self._stream_to_bot = stream_to_bot
        self._source = source
        self._maxlen = maxlen

    async def notify_user(self, max_user_id: int, text: str, *, fmt: str | None = None) -> str:
        """Вернуть UUID события — тот же ``event_id``, что в логах ядра и бота."""
        payload = NotifyUser(max_user_id=max_user_id, text=text, format=fmt)  # type: ignore[arg-type]
        event = await publish_event(
            self._redis,
            self._stream_to_bot,
            NOTIFY_USER,
            payload,
            source=self._source,
            maxlen=self._maxlen,
        )
        return event.id


async def _ensure_group(redis: Redis, stream: str, group: str) -> None:
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _delivery_counts(
    redis: Redis, stream: str, group: str, consumer: str, entries: list[tuple[str, Any]]
) -> dict[str, int]:
    """Сколько раз каждая из перехваченных записей уже доставлялась (XPENDING)."""
    if not entries:
        return {}
    # После XAUTOCLAIM записи принадлежат этому consumer'у: фильтр по нему не даёт
    # чужим pending-записям в том же диапазоне вытеснить наши из ответа.
    rows = await redis.xpending_range(
        stream,
        group,
        min=entries[0][0],
        max=entries[-1][0],
        count=len(entries),
        consumername=consumer,
    )
    return {str(row["message_id"]): int(row["times_delivered"]) for row in rows}


async def consume_stream(
    redis: Redis,
    stream: str,
    *,
    group: str,
    consumer: str,
    handlers: dict[str, EventHandler],
    stop: asyncio.Event,
    block_ms: int = 5000,
    batch: int = 32,
    stale_after_ms: int = 60_000,
    max_deliveries: int = 5,
) -> None:
    """Цикл потребителя: XAUTOCLAIM зависших → XREADGROUP новых → обработка → XACK.

    ``block_ms`` обязан быть меньше socket_timeout клиента (core.db.redis.new_client),
    иначе блокирующее чтение обрывается таймаутом сокета, а не ответом сервера.

    Правила подтверждения:
    - нет обработчика для типа — ack сразу (стрим общий, это не ошибка);
    - битая запись, невалидный payload или AppError — ack + запись в лог: повтор не поможет;
    - любая другая ошибка — событие остаётся pending и переиграется через
      ``stale_after_ms``; после ``max_deliveries`` попыток — ack + ошибка в лог,
      чтобы одно «ядовитое» событие не крутилось вечно.
    Потребитель обязан быть идемпотентным по ``Event.id``.
    """
    await _ensure_group(redis, stream, group)
    biz_info(logger, "events.consumer.started", stream=stream, group=group, consumer=consumer)

    async def _handle(stream_id: str, fields: dict[str, str], *, deliveries: int = 1) -> None:
        try:
            event = Event.from_fields(stream_id, fields)
        except EventDecodeError as exc:
            await redis.xack(stream, group, stream_id)
            biz_error(
                logger, "events.bad_envelope", stream=stream, stream_id=stream_id, error=str(exc)
            )
            return
        handler = handlers.get(event.type)
        if handler is None:
            await redis.xack(stream, group, stream_id)
            return
        try:
            await handler(event)
        except (ValidationError, AppError) as exc:
            await redis.xack(stream, group, stream_id)
            biz_error(
                logger,
                "events.handler.rejected",
                type=event.type,
                event_id=event.id,
                error=str(exc),
            )
            return
        except Exception:
            if deliveries >= max_deliveries:
                await redis.xack(stream, group, stream_id)
                biz_error(
                    logger,
                    "events.handler.dropped",
                    type=event.type,
                    event_id=event.id,
                    deliveries=deliveries,
                )
            else:
                biz_error(
                    logger,
                    "events.handler.failed",
                    type=event.type,
                    event_id=event.id,
                    deliveries=deliveries,
                    exc_info=True,
                )
            return
        await redis.xack(stream, group, stream_id)
        biz_info(logger, "events.handled", type=event.type, event_id=event.id, source=event.source)

    while not stop.is_set():
        try:
            # Сначала чужие зависшие сообщения (упавший потребитель), потом новые.
            _next, claimed, _deleted = await redis.xautoclaim(
                stream, group, consumer, min_idle_time=stale_after_ms, start_id="0-0", count=batch
            )
            counts = await _delivery_counts(redis, stream, group, consumer, claimed)
            for stream_id, fields in claimed:
                await _handle(stream_id, fields, deliveries=counts.get(stream_id, 1))

            response = await redis.xreadgroup(
                group, consumer, {stream: ">"}, count=batch, block=block_ms
            )
            for _stream, entries in response or []:
                for stream_id, fields in entries:
                    await _handle(stream_id, fields)
            if not response and not claimed:
                # Пустой опрос: отдать управление циклу событий. Настоящий Redis
                # блокирует XREADGROUP на block_ms, но клиент без блокировки
                # (fakeredis) иначе превратил бы цикл в busy-loop.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception:
            biz_warn(logger, "events.consumer.error", stream=stream, exc_info=True)
            await asyncio.sleep(1)

    biz_info(logger, "events.consumer.stopped", stream=stream, group=group)
