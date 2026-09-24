"""Потребитель событий бота внутри api на fakeredis: регистрация, ack чужих и битых событий,
переигрывание временных ошибок и предел доставок."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from core.api.events_worker import WorkerDeps, build_handlers
from core.db.repositories import UserRepository
from core.events import BOT_USER_STARTED, BotUserStarted, EventBus, consume_stream, publish_event
from core.files import FilesConfig


def _handlers(redis, *, llm=None, files: FilesConfig | None = None, fetch=None) -> dict:
    return build_handlers(
        WorkerDeps(
            redis=redis,
            bus=EventBus(redis, stream_to_bot="test:to_bot", source="api-test", maxlen=100),
            files=files or FilesConfig(Path("unused"), "soffice", 5),
            llm=llm,
            fetch=fetch,
        )
    )


async def _consume(
    redis,
    stream: str,
    handlers: dict,
    *,
    consumer: str = "test",
    timeout: float = 0.3,
    stop_after_calls: int | None = None,
    **kw,
) -> None:
    """Прогнать цикл потребителя до таймера либо до N вызовов обработчиков.

    Остановка по числу вызовов нужна тестам с stale_after_ms=0: иначе тот же
    потребитель перехватывал бы своё же pending-событие каждую итерацию.
    """
    stop = asyncio.Event()
    calls = 0

    def _counting(handler):
        async def wrapped(event):
            nonlocal calls
            calls += 1
            if stop_after_calls is not None and calls >= stop_after_calls:
                stop.set()
            await handler(event)

        return wrapped

    handle = asyncio.get_running_loop().call_later(timeout, stop.set)
    try:
        await consume_stream(
            redis,
            stream,
            group="core",
            consumer=consumer,
            handlers={name: _counting(h) for name, h in handlers.items()},
            stop=stop,
            block_ms=20,
            **kw,
        )
    finally:
        handle.cancel()


async def _pending(redis, stream: str) -> int:
    return int((await redis.xpending(stream, "core"))["pending"])


async def test_worker_registers_user_and_acks(db: None, session: AsyncSession, redis) -> None:
    stream = "test:to_core"
    await publish_event(
        redis,
        stream,
        BOT_USER_STARTED,
        BotUserStarted(
            max_user_id=555, chat_id=1, first_name="Bot", username="botuser", language_code="en"
        ),
        source="bot",
        maxlen=100,
    )
    await publish_event(redis, stream, "bot.unknown", {"x": 1}, source="bot", maxlen=100)
    await _consume(redis, stream, _handlers(redis))

    user = await UserRepository(session).get_by_max_id(555)
    assert user is not None and user.username == "botuser" and user.first_seen_via == "bot"
    assert user.language_code == "en"
    assert await _pending(redis, stream) == 0, "и обработанное, и чужое событие подтверждены"


async def test_invalid_payload_is_acked_not_retried(db: None, redis) -> None:
    stream = "test:to_core:invalid"
    await publish_event(
        redis, stream, BOT_USER_STARTED, {"max_user_id": "not-int"}, source="bot", maxlen=100
    )
    calls = 0

    async def handler(event):
        nonlocal calls
        calls += 1
        await _handlers(redis)[BOT_USER_STARTED](event)

    await _consume(redis, stream, {BOT_USER_STARTED: handler})
    assert calls == 1
    assert await _pending(redis, stream) == 0


async def test_broken_envelope_is_acked_without_dispatch(redis) -> None:
    stream = "test:to_core:envelope"
    await redis.xadd(stream, {"payload": "{}"})
    calls = 0

    async def handler(_event):
        nonlocal calls
        calls += 1

    await _consume(redis, stream, {BOT_USER_STARTED: handler})
    assert calls == 0
    assert await _pending(redis, stream) == 0


async def test_transient_failure_is_retried_then_dropped(redis) -> None:
    stream = "test:to_core:fail"
    await publish_event(
        redis, stream, BOT_USER_STARTED, {"max_user_id": 1, "chat_id": 1}, source="bot", maxlen=100
    )
    calls = 0

    async def failing(_event):
        nonlocal calls
        calls += 1
        raise RuntimeError("temporary")

    await _consume(redis, stream, {BOT_USER_STARTED: failing}, max_deliveries=3)
    assert calls == 1
    assert await _pending(redis, stream) == 1, "временная ошибка — событие ждёт повтора"

    # Другой потребитель перехватывает зависшее событие (вторая доставка) — снова провал, снова pending.
    await _consume(
        redis,
        stream,
        {BOT_USER_STARTED: failing},
        consumer="other",
        stale_after_ms=0,
        max_deliveries=3,
        stop_after_calls=1,
    )
    assert calls == 2
    assert await _pending(redis, stream) == 1

    # Третья доставка — последняя попытка: провал на ней даёт ack + events.handler.dropped.
    await _consume(
        redis,
        stream,
        {BOT_USER_STARTED: failing},
        consumer="third",
        stale_after_ms=0,
        max_deliveries=3,
        stop_after_calls=1,
    )
    assert calls == 3
    assert await _pending(redis, stream) == 0


async def test_bot_event_keeps_avatar_from_mini_app(
    db: None, session: AsyncSession, redis, auth_config, make_init_data
) -> None:
    from core.usecases.auth import login_with_init_data

    issued = await login_with_init_data(
        session,
        make_init_data(777, photo_url="https://cdn/avatar.png"),
        cfg=auth_config,
        admin_ids=frozenset(),
    )
    await session.commit()
    stream = "test:to_core:avatar"
    await publish_event(
        redis,
        stream,
        BOT_USER_STARTED,
        BotUserStarted(max_user_id=777, chat_id=1, first_name=""),
        source="bot",
        maxlen=10,
    )
    await _consume(redis, stream, _handlers(redis))
    user = await UserRepository(session).get_by_max_id(777)
    assert user is not None and user.photo_url == "https://cdn/avatar.png"
    assert user.first_name == issued.profile.first_name, (
        "пустое имя от бота не затирает имя из мини-аппа"
    )


def _by_user(event) -> str:
    return str(event.payload["max_user_id"])


async def test_different_users_are_handled_concurrently(redis) -> None:
    stream = "test:to_core:parallel"
    for user in (1, 2):
        await publish_event(
            redis, stream, "bot.test", {"max_user_id": user}, source="bot", maxlen=100
        )
    second_started = asyncio.Event()
    done: list[int] = []

    async def handler(event) -> None:
        user = event.payload["max_user_id"]
        if user == 1:
            # Строго последовательный потребитель здесь упёрся бы в таймаут.
            await asyncio.wait_for(second_started.wait(), timeout=1)
        else:
            second_started.set()
        done.append(user)

    await _consume(
        redis,
        stream,
        {"bot.test": handler},
        concurrency=2,
        partition=_by_user,
        stop_after_calls=2,
        timeout=2,
    )
    assert done == [2, 1]
    assert await _pending(redis, stream) == 0


async def test_events_of_one_user_keep_their_order(redis) -> None:
    stream = "test:to_core:order"
    for n in range(3):
        await publish_event(
            redis, stream, "bot.test", {"max_user_id": 7, "n": n}, source="bot", maxlen=100
        )
    log: list[str] = []

    async def handler(event) -> None:
        n = event.payload["n"]
        log.append(f"start {n}")
        await asyncio.sleep(0.01)
        log.append(f"end {n}")

    await _consume(
        redis,
        stream,
        {"bot.test": handler},
        concurrency=3,
        partition=_by_user,
        stop_after_calls=3,
        timeout=2,
    )
    assert log == ["start 0", "end 0", "start 1", "end 1", "start 2", "end 2"]


async def test_event_in_progress_is_not_redelivered(redis) -> None:
    """Перехват зависших не повторяет своё же событие, пока обработчик работает."""
    stream = "test:to_core:inflight"
    await publish_event(redis, stream, "bot.test", {"max_user_id": 1}, source="bot", maxlen=100)
    calls = 0

    async def slow(_event) -> None:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.2)

    await _consume(redis, stream, {"bot.test": slow}, stale_after_ms=0, concurrency=2, timeout=0.5)
    assert calls == 1
    assert await _pending(redis, stream) == 0


async def test_delivery_report_is_stitched_to_the_send(
    db: None, session: AsyncSession, redis, files_config: FilesConfig
) -> None:
    from core.db.repositories import DownloadTokenRepository
    from core.events import BOT_DOCUMENT_DELIVERY, BotDocumentDelivery, Event
    from core.usecases.documents import document_history, send_document_to_chat
    from tests.usecases.test_document_files import _ready_document
    from tests.usecases.test_documents import make_user

    user_id = await make_user(session, max_user_id=4242)
    document_id = await _ready_document(session, user_id)
    _, event_id = await send_document_to_chat(
        session,
        user_id=user_id,
        max_user_id=4242,
        document_id=document_id,
        fmt="docx",
        cfg=files_config,
        bus=EventBus(redis, stream_to_bot="test:to_bot", source="api-test", maxlen=100),
        tokens=DownloadTokenRepository(redis),
    )
    await session.commit()

    report = BotDocumentDelivery(
        max_user_id=4242,
        document_id=document_id,
        event_id=event_id,
        format="docx",
        status="failed",
        error="max_api.403",
    )
    await _handlers(redis, files=files_config)[BOT_DOCUMENT_DELIVERY](
        Event(type=BOT_DOCUMENT_DELIVERY, payload=report.model_dump(), source="bot", id="evt-r")
    )

    facts = await document_history(session, user_id=user_id, document_id=document_id)
    assert (facts[-1].kind, facts[-1].code) == ("delivery_failed", "max_api.403")
