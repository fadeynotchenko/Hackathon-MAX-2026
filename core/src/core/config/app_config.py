"""Сквозной конфиг: переменные, которые не принадлежат конкретному сервису.

Читается один раз на старте (``get_app_config`` кеширует), тесты сбрасывают
кеш через ``reset_app_config``. Секреты с узким scope сюда не кладём — они
живут в Config-классах владельцев (``core.usecases.auth.config`` и т.п.).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from core.config.env import get_env, get_env_bool, get_env_int, get_env_int_list, get_env_list
from core.config.env_spec import default_for


@dataclass(frozen=True)
class AppConfig:
    env: str
    log_level: str
    public_base_url: str
    admin_max_ids: frozenset[int]
    cors_allow_origins: tuple[str, ...]
    request_timeout_seconds: float
    dev_login_enabled: bool

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @classmethod
    def from_env(cls) -> AppConfig:
        env = get_env("ENV", default_for("ENV")).lower()
        if env not in {"dev", "production"}:
            # Опечатка вроде ENV=prod молча включила бы dev-режим (Swagger, CORS для localhost).
            raise ValueError(f"ENV={env!r}: допустимы dev и production")
        origins = tuple(get_env_list("CORS_ALLOW_ORIGINS"))
        if "*" in origins:
            # Со credentials Starlette отражал бы любой Origin — это выключает CORS целиком.
            raise ValueError("CORS_ALLOW_ORIGINS: * недопустим для API с cookie")
        return cls(
            env=env,
            log_level=get_env("LOG_LEVEL", default_for("LOG_LEVEL")).upper(),
            public_base_url=get_env("PUBLIC_BASE_URL").rstrip("/"),
            admin_max_ids=frozenset(get_env_int_list("ADMIN_MAX_IDS")),
            cors_allow_origins=origins,
            request_timeout_seconds=float(get_env_int("API_REQUEST_TIMEOUT_SECONDS", 30)),
            dev_login_enabled=get_env_bool("DEV_LOGIN_ENABLED", False),
        )


@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    return AppConfig.from_env()


def reset_app_config() -> None:
    """Сбросить кеш (только для тестов, которые меняют окружение)."""
    get_app_config.cache_clear()
