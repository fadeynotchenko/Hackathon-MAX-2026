"""Redis: конфиг и единственное соединение процесса (redis.asyncio)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote_plus

from redis.asyncio import Redis

from core.config.env import get_env, get_env_int
from core.config.env_spec import default_for

logger = logging.getLogger(__name__)

_client: Redis | None = None


@dataclass(frozen=True)
class RedisConfig:
    host: str
    port: int
    password: str
    db: int

    @classmethod
    def from_env(cls) -> RedisConfig:
        return cls(
            host=get_env("REDIS_HOST", default_for("REDIS_HOST")),
            port=get_env_int("REDIS_PORT", 6379),
            password=get_env("REDIS_PASSWORD"),
            db=get_env_int("REDIS_DB", 0),
        )

    def url(self) -> str:
        auth = f":{quote_plus(self.password)}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


# Потолок ожидания ответа. Обязан быть больше block_ms потребителя стримов
# (core.events.bus.consume_stream, 5 с): redis-py 8 по умолчанию ставит 5 с
# и обрывает блокирующий XREADGROUP ровно на границе.
SOCKET_TIMEOUT_SECONDS = 15


def new_client(cfg: RedisConfig) -> Redis:
    """Клиент с таймаутами проекта. Для блокирующих чтений заводится свой экземпляр,
    чтобы XREADGROUP не держал очередь команд остальных запросов."""
    return Redis.from_url(
        cfg.url(),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
        health_check_interval=30,
    )


async def init_redis(cfg: RedisConfig) -> Redis:
    global _client
    _client = new_client(cfg)
    await _client.ping()
    logger.info("redis ready", extra={"event": "redis.ready", "fields": {"host": cfg.host}})
    return _client


def use_redis(client: Redis) -> None:
    """Подменить клиент (тесты на fakeredis)."""
    global _client
    _client = client


def get_redis() -> Redis:
    if _client is None:
        raise RuntimeError("init_redis() не вызван")
    return _client


async def ping_redis() -> None:
    await get_redis().ping()


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
