"""Типизированное состояние приложения (``app.state.api``).

Создаётся в lifespan из окружения. Тесты собирают его руками (fakeredis в
EventBus), а фабрику сессий SQLite подменяют через db.base.use_session_maker.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from core.config.app_config import AppConfig
from core.events import EventBus
from core.files import FilesConfig
from core.llm import LLMClient
from core.usecases.auth.config import AuthConfig


@dataclass(frozen=True)
class ApiState:
    app_config: AppConfig
    auth_config: AuthConfig
    event_bus: EventBus
    files_config: FilesConfig
    llm: LLMClient | None = None


def api_state(request: Request) -> ApiState:
    state: ApiState | None = getattr(request.app.state, "api", None)
    if state is None:
        raise RuntimeError("app.state.api не инициализирован: lifespan не отработал")
    return state
