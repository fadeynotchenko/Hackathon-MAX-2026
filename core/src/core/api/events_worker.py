"""Потребитель событий бота (Redis Stream bot → core) внутри процесса api.

Отдельный контейнер здесь не нужен: consumer group переживает несколько
воркеров uvicorn (каждый — свой consumer в группе), а падение задачи видно в
/health как ``events_worker: error``.

Регистрация пользователя идемпотентна сама по себе. Диалог — нет: повторная
доставка сообщения снова позвала бы модель и прислала второй ответ, поэтому
обработанные ``Event.id`` запоминаются в Redis, как это делает бот.

Вложения (фото, сканы, голосовые) приходят ссылкой MAX: байты сценарий скачивает
сам через ``ChatActionDeps.download`` — событие остаётся маленьким.

События разных пользователей обрабатываются параллельно, одного — по очереди:
распознавание чужого фото не задерживает ответ на сообщение, а правка документа
не обгоняет его создание.
"""

from __future__ import annotations

import asyncio
import os
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import unescape

from redis.asyncio import Redis

from core.db import get_session
from core.db.repositories import DownloadTokenRepository
from core.events import (
    BOT_ATTACHMENT,
    BOT_CALLBACK,
    BOT_DOCUMENT_DELIVERY,
    BOT_MESSAGE,
    BOT_USER_STARTED,
    BotAttachment,
    BotCallback,
    BotDocumentDelivery,
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
    ChatAttachment,
    ChatReply,
    ChatSender,
    MediaFetcher,
    handle_chat_action,
    handle_chat_attachment,
    handle_chat_message,
)
from core.usecases.documents import record_delivery
from core.usecases.users import register_user_from_bot

CONSUMER_GROUP = "core"
PROCESSED_KEY = "events:processed:"
# Дольше, чем событие может висеть pending до исчерпания доставок.
PROCESSED_TTL_SECONDS = 7 * 24 * 3600
# Отметка «в работе» живёт недолго: если процесс убили посреди ответа модели,
# повторная доставка (через stale_after, 60 с) после неё выполнит работу, а не
# подтвердит событие без ответа.
IN_PROGRESS_TTL_SECONDS = 180
_DONE = "done"
_WORKING = "working"
# Двойное нажатие одной кнопки: бот снимает кнопки после первого, но второе
# успевает уйти. Одинаковое нажатие того же человека в это окно — дубль.
CALLBACK_KEY = "events:callback:"
CALLBACK_WINDOW_SECONDS = 5
# Предел текста сообщения в контракте notify.user (и в MAX).
MESSAGE_LIMIT = 4000
# Сколько событий бота обрабатывается одновременно. Обработчик держит соединение
# с БД, пока ждёт модель, поэтому предел ниже пула соединений (DB_POOL_SIZE).
WORKER_CONCURRENCY = 4


@dataclass(frozen=True)
class WorkerDeps:
    redis: Redis
    bus: EventBus
    files: FilesConfig
    llm: LLMClient | None
    fetch: MediaFetcher | None = None


async def on_user_started(event: Event) -> None:
    # ValidationError на битом payload — окончательная ошибка: consume_stream
    # подтвердит событие и запишет events.handler.rejected, повтора не будет.
    bind_context(request_id=event.id)
    data = BotUserStarted.model_validate(event.payload)
    async with get_session() as session:
        await register_user_from_bot(session, data)


def _buttons(reply: ChatReply) -> list[list[InlineButton]]:
    return [[InlineButton(text=b.text, payload=b.payload) for b in row] for row in reply.buttons]


_TAG = re.compile(r"<[^>]+>")


def _plain(html: str) -> str:
    """HTML ответа без разметки. Свои «<» и «&» в ответе экранированы, поэтому
    тегами здесь бывают только теги самого ответа."""
    return unescape(_TAG.sub("", html))


async def _reply(deps: WorkerDeps, max_user_id: int, reply: ChatReply) -> None:
    """Длинный ответ (расшифровка голосового плюс заполненные поля) обрезается, а не
    роняет событие: payload длиннее контракта не прошёл бы проверку NotifyUser.
    Обрезанный посреди тега HTML MAX не принял бы, поэтому такой ответ уходит
    простым текстом."""
    text: str = reply.text
    fmt: str | None = "html"
    if len(text) > MESSAGE_LIMIT:
        text, fmt = _plain(text), None
        if len(text) > MESSAGE_LIMIT:
            text = text[: MESSAGE_LIMIT - 1] + "…"
    await deps.bus.notify_user(max_user_id, text, fmt=fmt, buttons=_buttons(reply))


class EventInProgressError(RuntimeError):
    """То же событие уже в работе (или процесс упал посреди неё): не подтверждать,
    а переиграть позже, когда отметка «в работе» истечёт."""


async def _once(deps: WorkerDeps, event: Event, work: Callable[[], Awaitable[None]]) -> None:
    """Выполнить работу один раз на Event.id; при сбое снять отметку, чтобы повтор был возможен."""
    key = f"{PROCESSED_KEY}{event.id}"
    if not await deps.redis.set(key, _WORKING, ex=IN_PROGRESS_TTL_SECONDS, nx=True):
        if await deps.redis.get(key) == _WORKING:
            raise EventInProgressError(event.id)
        return
    try:
        await work()
    except BaseException:
        await deps.redis.delete(key)
        raise
    await deps.redis.set(key, _DONE, ex=PROCESSED_TTL_SECONDS)


def build_handlers(deps: WorkerDeps) -> dict[str, EventHandler]:
    action_deps = ChatActionDeps(
        files=deps.files,
        bus=deps.bus,
        tokens=DownloadTokenRepository(deps.redis),
        llm=deps.llm,
        fetch=deps.fetch,
    )

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
            await _reply(deps, data.max_user_id, reply)

        await _once(deps, event, work)

    async def on_callback(event: Event) -> None:
        bind_context(request_id=event.id)
        data = BotCallback.model_validate(event.payload)
        tap = f"{CALLBACK_KEY}{data.max_user_id}:{data.payload}"
        first = await deps.redis.set(tap, event.id, ex=CALLBACK_WINDOW_SECONDS, nx=True)
        if not first and await deps.redis.get(tap) != event.id:
            # Второе «Прислать PDF» собрало бы и отправило файл ещё раз.
            return

        async def work() -> None:
            async with get_session() as session:
                reply = await handle_chat_action(
                    session,
                    sender=ChatSender(data.max_user_id),
                    payload=data.payload,
                    deps=action_deps,
                )
            await _reply(deps, data.max_user_id, reply)

        await _once(deps, event, work)

    async def on_attachment(event: Event) -> None:
        bind_context(request_id=event.id)
        data = BotAttachment.model_validate(event.payload)
        sender = ChatSender(data.max_user_id, data.first_name, data.last_name, data.username)
        attachment = ChatAttachment(
            kind=data.kind, url=data.url, filename=data.filename, caption=data.text
        )

        async def work() -> None:
            async with get_session() as session:
                reply = await handle_chat_attachment(
                    session, sender=sender, attachment=attachment, deps=action_deps
                )
            await _reply(deps, data.max_user_id, reply)

        await _once(deps, event, work)

    async def on_delivery(event: Event) -> None:
        bind_context(request_id=event.id)
        data = BotDocumentDelivery.model_validate(event.payload)

        async def work() -> None:
            async with get_session() as session:
                await record_delivery(
                    session,
                    max_user_id=data.max_user_id,
                    document_id=data.document_id,
                    event_id=data.event_id,
                    fmt=data.format,
                    delivered=data.status == "delivered",
                    error=data.error,
                )

        await _once(deps, event, work)

    return {
        BOT_USER_STARTED: on_user_started,
        BOT_MESSAGE: on_message,
        BOT_CALLBACK: on_callback,
        BOT_ATTACHMENT: on_attachment,
        BOT_DOCUMENT_DELIVERY: on_delivery,
    }


def consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def by_user(event: Event) -> str | None:
    """Ключ очереди: реплики одного пользователя идут строго друг за другом."""
    user = event.payload.get("max_user_id")
    return str(user) if user is not None else None


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
        concurrency=WORKER_CONCURRENCY,
        partition=by_user,
    )
