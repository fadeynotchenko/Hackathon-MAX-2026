"""Настройки GigaChat. Пустой ключ авторизации — агент выключен, остальное работает."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config.env import get_env, get_env_int, get_env_or_default

CORE_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class GigaChatConfig:
    auth_key: str
    scope: str
    model: str
    api_url: str
    auth_url: str
    ca_bundle: Path
    timeout_seconds: int
    # Сколько запросов к модели идёт одновременно: на тарифе физлиц GigaChat
    # держит один поток и на второй параллельный отвечает 429.
    max_concurrency: int = 1

    @property
    def enabled(self) -> bool:
        return bool(self.auth_key)

    @classmethod
    def from_env(cls) -> GigaChatConfig:
        return cls(
            auth_key=get_env("GIGACHAT_AUTH_KEY"),
            scope=get_env_or_default("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            model=get_env_or_default("GIGACHAT_MODEL", "GigaChat-3-Ultra"),
            api_url=get_env_or_default("GIGACHAT_API_URL", "https://api.giga.chat/v1").rstrip("/"),
            auth_url=get_env_or_default(
                "GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
            ),
            ca_bundle=CORE_ROOT
            / get_env_or_default("GIGACHAT_CA_BUNDLE", "certs/russian_trusted_root_ca.pem"),
            timeout_seconds=get_env_int("GIGACHAT_TIMEOUT_SECONDS", 20),
            max_concurrency=max(1, get_env_int("GIGACHAT_MAX_CONCURRENCY", 1)),
        )
