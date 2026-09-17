"""Конфиг аутентификации мини-аппа: секрет JWT, TTL токенов, возраст initData."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from core.config.env import get_env, get_env_int

_MIN_SECRET_LEN = 32


@dataclass(frozen=True)
class AuthConfig:
    bot_token: str
    jwt_secret: str
    access_ttl_seconds: int
    refresh_ttl_seconds: int
    init_data_max_age_seconds: int

    @classmethod
    def from_env(cls) -> AuthConfig:
        return cls(
            bot_token=get_env("MAX_BOT_TOKEN"),
            jwt_secret=get_env("JWT_SECRET"),
            access_ttl_seconds=get_env_int("ACCESS_TOKEN_TTL_SECONDS", 900),
            refresh_ttl_seconds=get_env_int("REFRESH_TOKEN_TTL_SECONDS", 30 * 24 * 3600),
            init_data_max_age_seconds=get_env_int("INIT_DATA_MAX_AGE_SECONDS", 3600),
        )

    def validate(self) -> None:
        if not self.bot_token:
            raise ValueError("MAX_BOT_TOKEN не задан")
        if len(self.jwt_secret) < _MIN_SECRET_LEN:
            raise ValueError(f"JWT_SECRET короче {_MIN_SECRET_LEN} символов")
        if self.access_ttl_seconds < 60 or self.refresh_ttl_seconds <= self.access_ttl_seconds:
            raise ValueError("TTL токенов: access >= 60 c, refresh > access")


@lru_cache(maxsize=1)
def get_auth_config() -> AuthConfig:
    cfg = AuthConfig.from_env()
    cfg.validate()
    return cfg


def reset_auth_config() -> None:
    get_auth_config.cache_clear()
