"""Потребитель событий бота (Redis Stream bot → core) внутри процесса api.

Отдельный контейнер здесь не нужен: обработчик идемпотентен, consumer group
переживает несколько воркеров uvicorn (каждый — свой consumer в группе), а
падение задачи видно в /health как ``events_worker: error``.
"""

from __future__ import annotations

import asyncio
import os
import socket

from redis.asyncio import Redis

from core.db import get_session
from core.events import BOT_USER_STARTED, BotUserStarted, Event, consume_stream
from core.logs import bind_context
from core.usecases.users import register_user_from_bot

CONSUMER_GROUP = "core"


async def on_user_started(event: Event) -> None:
    # ValidationError на битом payload — окончательная ошибка: consume_stream
    # подтвердит событие и запишет events.handler.rejected, повтора не будет.
    bind_context(request_id=event.id)
    data = BotUserStarted.model_validate(event.payload)
    async with get_session() as session:
        await register_user_from_bot(session, data)


HANDLERS = {BOT_USER_STARTED: on_user_started}


def consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def run_events_worker(redis: Redis, *, stream: str, stop: asyncio.Event) -> None:
    await consume_stream(
        redis, stream, group=CONSUMER_GROUP, consumer=consumer_name(), handlers=HANDLERS, stop=stop
    )
