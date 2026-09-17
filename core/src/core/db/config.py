"""Конфиг PostgreSQL: DSN и параметры пула из окружения."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from core.config.env import get_env, get_env_int
from core.config.env_spec import default_for

# Потолок соединений на один процесс: API_WORKERS × (pool + overflow) должно
# оставаться ниже max_connections Postgres (100 в прод-compose).
# Это страховка от опечатки вида DB_POOL_SIZE=100 в .env.
_MAX_TOTAL_PER_PROCESS = 30


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 10
    pool_recycle: int = 1800
    statement_timeout_ms: int = 30000

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        return cls(
            host=get_env("DB_HOST", default_for("DB_HOST")),
            port=get_env_int("DB_PORT", 5432),
            user=get_env("DB_USER"),
            password=get_env("DB_PASSWORD"),
            database=get_env("DB_NAME"),
            pool_size=get_env_int("DB_POOL_SIZE", 5),
            max_overflow=get_env_int("DB_MAX_OVERFLOW", 10),
            pool_timeout=get_env_int("DB_POOL_TIMEOUT", 10),
            pool_recycle=get_env_int("DB_POOL_RECYCLE", 1800),
            statement_timeout_ms=get_env_int("DB_STATEMENT_TIMEOUT_MS", 30000),
        )

    def validate(self) -> None:
        for name, value in (
            ("DB_USER", self.user),
            ("DB_PASSWORD", self.password),
            ("DB_NAME", self.database),
        ):
            if not value:
                raise ValueError(f"{name} не задан")
        if self.pool_size < 1 or self.max_overflow < 0 or self.pool_timeout < 1:
            raise ValueError("параметры пула БД вне допустимых границ")
        if self.statement_timeout_ms < 1000:
            raise ValueError("DB_STATEMENT_TIMEOUT_MS должен быть >= 1000")
        if self.pool_size + self.max_overflow > _MAX_TOTAL_PER_PROCESS:
            raise ValueError(
                f"DB_POOL_SIZE + DB_MAX_OVERFLOW > {_MAX_TOTAL_PER_PROCESS}: "
                "поднимите max_connections Postgres и лимит в db/config.py осознанно"
            )

    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.database}"
        )
