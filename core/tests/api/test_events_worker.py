"""Потребитель событий бота внутри api на fakeredis: регистрация, ack чужих и битых событий,
переигрывание временных ошибок и предел доставок."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from core.api.events_worker import HANDLERS
from core.db.repositories import UserRepository
from core.events import BOT_USER_STARTED, BotUserStarted, consume_stream, publish_event


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
    await _consume(redis, stream, HANDLERS)

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
        await HANDLERS[BOT_USER_STARTED](event)

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
    await _consume(redis, stream, HANDLERS)
    user = await UserRepository(session).get_by_max_id(777)
    assert user is not None and user.photo_url == "https://cdn/avatar.png"
    assert user.first_name == issued.profile.first_name, (
        "пустое имя от бота не затирает имя из мини-аппа"
    )
