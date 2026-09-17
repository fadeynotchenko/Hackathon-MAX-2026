"""Настройка логирования процесса core: один формат для api, джоб и (через pino) бота.

Два выхода:
- stdout — JSON-строки (прод, docker) либо цветной текст (терминал разработчика);
- файл ``<LOG_DIR>/<service>.log`` — всегда JSON, посуточная ротация, gzip.

Схема JSON-записи (совпадает с bot/src/logger.ts):
``ts, level, service, logger, event, msg, request_id, user_id, <поля события>, err``
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import sys
import traceback
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from core.config.env import get_env, get_env_or_default
from core.config.env_spec import default_for

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[35m",
}
_EVENT_COLOR = "\033[1;35m"
_KEY_COLOR = "\033[33m"

# Стандартные атрибуты LogRecord: всё остальное в record.__dict__ — это extra.
_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
        "event",
        "fields",
    }
)


def _record_fields(record: logging.LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = dict(getattr(record, "fields", None) or {})
    # extra={"foo": 1} из сторонних библиотек тоже попадает в запись.
    for key, value in record.__dict__.items():
        if key not in _RESERVED and key not in fields and not key.startswith("_"):
            fields[key] = value
    return fields


def _error_payload(record: logging.LogRecord) -> dict[str, Any] | None:
    if not record.exc_info:
        return None
    exc_type, exc, tb = record.exc_info
    return {
        "type": exc_type.__name__ if exc_type else None,
        "message": str(exc) if exc else None,
        "stack": "".join(traceback.format_exception(exc_type, exc, tb)),
    }


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": self._service,
            "logger": record.name,
        }
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        payload["msg"] = record.getMessage()
        payload.update(_record_fields(record))
        if err := _error_payload(record):
            payload["err"] = err
        return json.dumps(payload, ensure_ascii=False, default=str)


class PrettyFormatter(logging.Formatter):
    """Однострочный формат для терминала: время, уровень, сервис, событие, поля."""

    def __init__(self, service: str, *, color: bool) -> None:
        super().__init__()
        self._service = service
        self._color = color

    def _paint(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self._color else text

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        level = self._paint(f"{record.levelname:<5}", _LEVEL_COLORS.get(record.levelno, "") + _BOLD)
        parts = [self._paint(ts, _DIM), level, self._paint(f"{self._service:<6}", _DIM)]
        event = getattr(record, "event", None)
        message = record.getMessage()
        if event:
            parts.append(self._paint(event, _EVENT_COLOR))
            if message and message != event:
                parts.append(message)
        else:
            parts.append(f"{self._paint(record.name, _DIM)} {message}")
        for key, value in _record_fields(record).items():
            rendered = (
                json.dumps(value, ensure_ascii=False, default=str)
                if not isinstance(value, str)
                else value
            )
            parts.append(f"{self._paint(key, _KEY_COLOR)}={rendered}")
        line = " ".join(parts)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def _gzip_rotator(source: str, dest: str) -> None:
    with open(source, "rb") as src, gzip.open(dest, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.remove(source)


def _gzip_namer(name: str) -> str:
    """``api.log.2026-09-16`` → ``api.2026-09-16.log.gz``: тот же шаблон имён, что у бота (pino-roll)."""
    path = Path(name)
    stem, _, date = path.name.partition(".log.")
    if date:
        return str(path.with_name(f"{stem}.{date}.log.gz"))
    return name + ".gz"


def _resolve_format(explicit: str | None) -> str:
    value = (explicit or get_env("LOG_FORMAT", default_for("LOG_FORMAT"))).lower()
    if value in {"json", "pretty"}:
        return value
    return "pretty" if sys.stdout.isatty() else "json"


def setup_logging(
    service: str,
    *,
    level: str | None = None,
    fmt: str | None = None,
    log_dir: str | Path | None = None,
) -> logging.Logger:
    """Сконфигурировать root-логгер процесса и вернуть логгер сервиса.

    Повторный вызов пересобирает хендлеры (нужно тестам). ``log_dir=""``
    отключает файловый лог; по умолчанию берётся LOG_DIR из окружения.
    """
    level_name = (level or get_env("LOG_LEVEL", default_for("LOG_LEVEL"))).upper()
    output_format = _resolve_format(fmt)
    directory = (
        get_env_or_default("LOG_DIR", default_for("LOG_DIR")) if log_dir is None else str(log_dir)
    )

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    console = logging.StreamHandler(sys.stdout)
    if output_format == "json":
        console.setFormatter(JsonFormatter(service))
    else:
        console.setFormatter(PrettyFormatter(service, color=sys.stdout.isatty()))
    root.addHandler(console)

    if directory:
        try:
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            file_handler = TimedRotatingFileHandler(
                path / f"{service}.log", when="midnight", utc=True, backupCount=0, encoding="utf-8"
            )
        except OSError as exc:
            # Каталог логов недоступен (bind-mount с чужим владельцем): работать без
            # файла лучше, чем не стартовать; stdout остаётся всегда.
            logging.getLogger(__name__).warning(
                "file log disabled",
                extra={
                    "event": "logs.file_unavailable",
                    "fields": {"dir": directory, "error": str(exc)},
                },
            )
            return logging.getLogger(service)
        # backupCount=0 означает «не удалять»: историю чистит человек или джоба,
        # а gzip делает годы суточных файлов дешёвыми по диску.
        file_handler.rotator = _gzip_rotator
        file_handler.namer = _gzip_namer
        file_handler.setFormatter(JsonFormatter(service))
        root.addHandler(file_handler)

    # Шумные библиотеки — только предупреждения; access-лог uvicorn заменён
    # нашим middleware (тот же формат, что у бизнес-событий).
    for name in ("httpx", "httpcore", "sqlalchemy.engine", "asyncio", "alembic"):
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers = []
        uv.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False

    return logging.getLogger(service)
