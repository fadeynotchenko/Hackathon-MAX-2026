"""Контракты событий: round-trip модель → конверт → стрим → конверт → модель."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.events import (
    BOT_USER_STARTED,
    ENVELOPE_VERSION,
    EVENT_PAYLOADS,
    NOTIFY_USER,
    BotUserStarted,
    Event,
    EventBus,
    EventDecodeError,
    NotifyUser,
    publish_event,
)


def test_envelope_roundtrip_keeps_version_and_id() -> None:
    event = Event(
        type=NOTIFY_USER, payload={"max_user_id": 1, "text": "hi", "format": None}, source="api"
    )
    fields = event.to_fields()
    assert fields["v"] == str(ENVELOPE_VERSION)
    restored = Event.from_fields("1-0", fields)
    assert restored.id == event.id and restored.v == event.v and restored.type == event.type
    assert restored.payload == event.payload and restored.stream_id == "1-0"


@pytest.mark.parametrize(
    "fields",
    [
        {"payload": "{}"},
        {"type": NOTIFY_USER, "payload": "not json"},
        {"type": NOTIFY_USER, "payload": "[1,2]"},
        {"type": NOTIFY_USER, "payload": "{}", "v": "x"},
    ],
)
def test_broken_envelope_fails_fast(fields: dict[str, str]) -> None:
    with pytest.raises(EventDecodeError):
        Event.from_fields("1-0", fields)


def test_from_fields_defaults_version_for_legacy_records() -> None:
    event = Event.from_fields("1-0", {"type": NOTIFY_USER, "payload": "{}"})
    assert event.v == ENVELOPE_VERSION and event.id == "1-0"


@pytest.mark.parametrize(
    ("event_type", "sample"),
    [
        (NOTIFY_USER, {"max_user_id": 5, "text": "hello", "format": "markdown"}),
        (
            BOT_USER_STARTED,
            {
                "max_user_id": 5,
                "chat_id": 10,
                "first_name": "A",
                "last_name": None,
                "username": "a",
                "language_code": "ru",
                "start_payload": "ref",
            },
        ),
    ],
)
def test_payload_models_roundtrip(event_type: str, sample: dict) -> None:
    model = EVENT_PAYLOADS[event_type]
    payload = model.model_validate(sample)
    event = Event(type=event_type, payload=payload.model_dump(), source="test")
    restored = model.model_validate(Event.from_fields("1-0", event.to_fields()).payload)
    assert restored == payload


def test_payload_models_reject_unknown_and_invalid_fields() -> None:
    with pytest.raises(ValidationError):
        NotifyUser.model_validate({"max_user_id": 1, "text": "x", "fmt": "html"})
    with pytest.raises(ValidationError):
        NotifyUser.model_validate({"max_user_id": 0, "text": "x"})
    with pytest.raises(ValidationError):
        BotUserStarted.model_validate({"max_user_id": "not-int", "chat_id": 1})


async def test_publish_returns_event_with_uuid_and_stream_id(redis) -> None:
    event = await publish_event(
        redis, "s", NOTIFY_USER, NotifyUser(max_user_id=1, text="x"), source="t", maxlen=10
    )
    assert len(event.id) == 32 and event.stream_id and "-" in event.stream_id
    bus = EventBus(redis, stream_to_bot="s", source="t", maxlen=10)
    event_id = await bus.notify_user(2, "y", fmt="html")
    entries = await redis.xrange("s")
    assert len(entries) == 2
    assert entries[1][1]["id"] == event_id and entries[1][1]["v"] == "1"


def test_blocking_read_fits_into_socket_timeout() -> None:
    """XREADGROUP BLOCK должен завершаться ответом сервера, а не таймаутом сокета клиента."""
    import inspect

    from core.db.redis import SOCKET_TIMEOUT_SECONDS
    from core.events.bus import consume_stream

    block_ms = inspect.signature(consume_stream).parameters["block_ms"].default
    assert block_ms < SOCKET_TIMEOUT_SECONDS * 1000
