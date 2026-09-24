"""Потребитель событий бота (Redis Stream bot → core) внутри процесса api.

Отдельный контейнер здесь не нужен: consumer group переживает несколько
воркеров uvicorn (каждый — свой consumer в группе), а падение задачи видно в
/health как ``events_worker: error``.

Регистрация пользователя идемпотентна сама по себе. Диалог — нет: повторная
доставка сообщения снова позвала бы модель и прислала второй ответ, поэтому
обработанные ``Event.id`` запоминаются в Redis, как это делает бот.
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from redis.asyncio import Redis

from core.db import get_session
from core.db.repositories import DownloadTokenRepository
from core.events import (
    BOT_CALLBACK,
    BOT_MESSAGE,
    BOT_USER_STARTED,
    BotCallback,
    BotMessage,
    BotUserStarted,
    Event,
    EventBus,
    EventHandler,
    InlineButton,
    consume_stream,
)
from core.files import FilesConfig
from core.llm import LLMClient
from core.logs import bind_context
from core.usecases.agent import (
    ChatActionDeps,
    ChatReply,
    ChatSender,
    handle_chat_action,
    handle_chat_message,
)
from core.usecases.users import register_user_from_bot

CONSUMER_GROUP = "core"
PROCESSED_KEY = "events:processed:"
# Дольше, чем событие может висеть pending до исчерпания доставок.
PROCESSED_TTL_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True)
class WorkerDeps:
    redis: Redis
    bus: EventBus
    files: FilesConfig
    llm: LLMClient | None


async def on_user_started(event: Event) -> None:
    # ValidationError на битом payload — окончательная ошибка: consume_stream
    # подтвердит событие и запишет events.handler.rejected, повтора не будет.
    bind_context(request_id=event.id)
    data = BotUserStarted.model_validate(event.payload)
    async with get_session() as session:
        await register_user_from_bot(session, data)


def _buttons(reply: ChatReply) -> list[list[InlineButton]]:
    return [[InlineButton(text=b.text, payload=b.payload) for b in row] for row in reply.buttons]


async def _once(deps: WorkerDeps, event: Event, work: Callable[[], Awaitable[None]]) -> None:
    """Выполнить работу один раз на Event.id; при сбое снять отметку, чтобы повтор был возможен."""
    key = f"{PROCESSED_KEY}{event.id}"
    if not await deps.redis.set(key, "1", ex=PROCESSED_TTL_SECONDS, nx=True):
        return
    try:
        await work()
    except BaseException:
        await deps.redis.delete(key)
        raise


def build_handlers(deps: WorkerDeps) -> dict[str, EventHandler]:
    async def on_message(event: Event) -> None:
        bind_context(request_id=event.id)
        data = BotMessage.model_validate(event.payload)
        sender = ChatSender(data.max_user_id, data.first_name, data.last_name, data.username)

        async def work() -> None:
            # Ответ публикуется после коммита сессии: нажатая следом кнопка
            # должна увидеть документ, который этот ответ описывает.
            async with get_session() as session:
                reply = await handle_chat_message(
                    session, sender=sender, text=data.text, llm=deps.llm
                )
            await deps.bus.notify_user(data.max_user_id, reply.text, buttons=_buttons(reply))

        await _once(deps, event, work)

    async def on_callback(event: Event) -> None:
        bind_context(request_id=event.id)
        data = BotCallback.model_validate(event.payload)
        action_deps = ChatActionDeps(
            files=deps.files, bus=deps.bus, tokens=DownloadTokenRepository(deps.redis)
        )

        async def work() -> None:
            async with get_session() as session:
                reply = await handle_chat_action(
                    session,
                    sender=ChatSender(data.max_user_id),
                    payload=data.payload,
                    deps=action_deps,
                )
            await deps.bus.notify_user(data.max_user_id, reply.text, buttons=_buttons(reply))

        await _once(deps, event, work)

    return {
        BOT_USER_STARTED: on_user_started,
        BOT_MESSAGE: on_message,
        BOT_CALLBACK: on_callback,
    }


def consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def run_events_worker(
    redis: Redis, *, stream: str, stop: asyncio.Event, deps: WorkerDeps
) -> None:
    await consume_stream(
        redis,
        stream,
        group=CONSUMER_GROUP,
        consumer=consumer_name(),
        handlers=build_handlers(deps),
        stop=stop,
    )
