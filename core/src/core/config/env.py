"""Единственное место, где читается ``os.environ``.

Все Config-классы (``core.usecases.auth.config``, ``core.db.config``, ``core.db.redis``)
ходят в окружение только через эти хелперы. Тест-замок
``tests/config/test_env_spec.py`` проверяет, что прямых ``os.getenv`` в коде
нет, а каждое имя переменной описано в реестре ``env_spec.py``.

Локально переменные приходят из ``.env`` (python-dotenv), в контейнерах —
из ``env_file`` compose. ``load_dotenv`` не перекрывает уже заданные
переменные, поэтому compose-значения всегда побеждают файл.
"""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", ""})


def get_env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def get_env_or_default(key: str, default: str) -> str:
    """Как get_env, но явно пустое значение (``LOG_DIR=``) остаётся пустым, а не
    подменяется дефолтом: так переменную можно выключить, не удаляя из .env."""
    value = os.getenv(key)
    return default if value is None else value.strip()


def get_env_int(key: str, default: int) -> int:
    """Целое из env. Невалидное значение ⇒ дефолт и warning, а не тихий откат:
    молчаливый фолбэк маскирует опечатку на проде как «изменение применилось»."""
    raw = get_env(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("env %s=%r is not an integer; using default %d", key, raw, default)
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    raw = get_env(key).lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return default if raw == "" else False
    logger.warning("env %s=%r is not a boolean; using default %s", key, raw, default)
    return default


def get_env_list(key: str) -> list[str]:
    """Список строк: JSON-массив (``["a","b"]``) или CSV (``a,b``)."""
    raw = get_env(key)
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("env %s is not valid JSON; treating as CSV", key)
        else:
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_env_int_list(key: str) -> list[int]:
    out: list[int] = []
    for item in get_env_list(key):
        try:
            out.append(int(item))
        except ValueError:
            logger.warning("env %s: skipping non-integer item %r", key, item)
    return out
