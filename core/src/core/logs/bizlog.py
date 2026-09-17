"""Структурированные бизнес-события поверх стандартного logging.

Одно действие пользователя или системы = одна запись с машинным именем
события (``auth.login.ok``) и полями-kwargs. Formatter (``setup.py``)
превращает это в JSON-строку или в цветную строку для терминала — формат
общий с ботом (pino), см. docs/LOGGING.md.

``request_id`` и ``user_id`` живут в contextvars: middleware API привязывает
их один раз на запрос, и каждая запись ниже по стеку получает их автоматически.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

_MAX_VALUE_LEN = 500
_UNSET = object()

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("user_id", default=None)


def bind_context(*, request_id: Any = _UNSET, user_id: Any = _UNSET) -> None:
    """Привязать идентификаторы к текущему контексту исполнения (запрос, апдейт, прогон джобы)."""
    if request_id is not _UNSET:
        _request_id.set(request_id)
    if user_id is not _UNSET:
        _user_id.set(user_id)


def clear_context() -> None:
    _request_id.set(None)
    _user_id.set(None)


def sanitize_value(value: Any) -> Any:
    """Значения полей: скаляры как есть, строки обрезаем, прочее — через str()."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value if len(value) <= _MAX_VALUE_LEN else value[: _MAX_VALUE_LEN - 1] + "…"
    if isinstance(value, list | tuple | set | frozenset):
        return [sanitize_value(v) for v in list(value)[:50]]
    if isinstance(value, dict):
        return {str(k): sanitize_value(v) for k, v in list(value.items())[:50]}
    try:
        return sanitize_value(str(value))
    except Exception:
        return "<unprintable>"


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    msg: str = "",
    *,
    exc_info: Any = None,
    **fields: Any,
) -> None:
    """Базовый вызов: событие + поля. Контекст (request_id, user_id) подмешивается сам."""
    if "request_id" not in fields and (rid := _request_id.get()) is not None:
        fields["request_id"] = rid
    if "user_id" not in fields and (uid := _user_id.get()) is not None:
        fields["user_id"] = uid
    logger.log(
        level,
        msg or event,
        exc_info=exc_info,
        extra={"event": event, "fields": {k: sanitize_value(v) for k, v in fields.items()}},
    )


def biz_info(logger: logging.Logger, event: str, msg: str = "", **fields: Any) -> None:
    log_event(logger, logging.INFO, event, msg, **fields)


def biz_warn(logger: logging.Logger, event: str, msg: str = "", **fields: Any) -> None:
    log_event(logger, logging.WARNING, event, msg, **fields)


def biz_error(
    logger: logging.Logger, event: str, msg: str = "", *, exc_info: Any = None, **fields: Any
) -> None:
    log_event(logger, logging.ERROR, event, msg, exc_info=exc_info, **fields)
