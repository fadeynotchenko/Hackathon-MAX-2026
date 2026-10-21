"""Настройки DaData. Пустой ключ — подсказки выключены, поля заполняются руками."""

from __future__ import annotations

from dataclasses import dataclass

from core.config.env import get_env, get_env_int, get_env_or_default


@dataclass(frozen=True)
class DadataConfig:
    api_key: str
    api_url: str
    timeout_seconds: int

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> DadataConfig:
        return cls(
            api_key=get_env("DADATA_API_KEY"),
            api_url=get_env_or_default(
                "DADATA_API_URL", "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
            ).rstrip("/"),
            timeout_seconds=get_env_int("DADATA_TIMEOUT_SECONDS", 5),
        )
