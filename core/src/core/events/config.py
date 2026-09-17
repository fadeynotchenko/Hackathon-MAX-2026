"""Имена стримов Redis: ядро → бот и бот → ядро."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from core.config.env import get_env, get_env_int
from core.config.env_spec import default_for


@dataclass(frozen=True)
class EventsConfig:
    stream_to_bot: str
    stream_to_core: str
    maxlen: int

    @classmethod
    def from_env(cls) -> EventsConfig:
        return cls(
            stream_to_bot=get_env("EVENTS_STREAM_TO_BOT", default_for("EVENTS_STREAM_TO_BOT")),
            stream_to_core=get_env("EVENTS_STREAM_TO_CORE", default_for("EVENTS_STREAM_TO_CORE")),
            maxlen=get_env_int("EVENTS_STREAM_MAXLEN", 10000),
        )


@lru_cache(maxsize=1)
def get_events_config() -> EventsConfig:
    return EventsConfig.from_env()
