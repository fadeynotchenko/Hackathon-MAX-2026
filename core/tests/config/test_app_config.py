"""AppConfig: недопустимые значения окружения падают на старте, а не молча."""

from __future__ import annotations

import pytest

from core.config.app_config import AppConfig, reset_app_config


@pytest.fixture(autouse=True)
def _reset():
    reset_app_config()
    yield
    reset_app_config()


def test_env_must_be_dev_or_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    with pytest.raises(ValueError, match="ENV="):
        AppConfig.from_env()


def test_wildcard_cors_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
        AppConfig.from_env()


def test_dev_login_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEV_LOGIN_ENABLED", raising=False)
    assert AppConfig.from_env().dev_login_enabled is False
