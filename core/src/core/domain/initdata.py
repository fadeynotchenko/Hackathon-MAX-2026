"""Проверка подписи initData мини-приложения MAX.

Алгоритм (https://dev.max.ru/docs/webapps/validation):
1. initData — строка вида ``query_id=...&user=...&auth_date=...&hash=...``.
   Разбираем её в пары, URL-декодируем значения.
2. Убираем ``hash``; оставшиеся пары сортируем по ключу и склеиваем
   переводом строки: ``key1=value1\\nkey2=value2``.
3. ``secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)``.
4. ``signature = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))``.
5. Сравниваем с ``hash`` за константное время; ``auth_date`` не старше
   ``max_age_seconds``.

Функция ``build_init_data`` — обратная операция для тестов и dev-режима
(``core.scripts.dev_init_data``): подписывает произвольные параметры тем же
токеном, чтобы мини-апп можно было открыть в обычном браузере.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode

_SECRET_SALT = b"WebAppData"
# Часы клиента и сервера расходятся; auth_date «из будущего» в пределах минуты — норма.
_FUTURE_SKEW_SECONDS = 60


class InitDataError(ValueError):
    """Ошибка проверки initData. ``code`` — машинная причина для логов и ответа API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MaxUser:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    photo_url: str | None = None

    @property
    def display_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part) or str(self.id)


@dataclass(frozen=True)
class MaxChat:
    id: int
    type: str


@dataclass(frozen=True)
class InitData:
    user: MaxUser
    auth_date: int
    query_id: str | None = None
    start_param: str | None = None
    chat: MaxChat | None = None


def secret_key(bot_token: str) -> bytes:
    return hmac.new(_SECRET_SALT, bot_token.encode("utf-8"), hashlib.sha256).digest()


def data_check_string(pairs: dict[str, str]) -> str:
    return "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))


def sign(pairs: dict[str, str], bot_token: str) -> str:
    """Подпись для набора пар без ``hash``."""
    return hmac.new(
        secret_key(bot_token), data_check_string(pairs).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def parse_pairs(raw: str) -> dict[str, str]:
    if not raw or not raw.strip():
        raise InitDataError("empty", "initData пуст")
    pairs = parse_qsl(raw, keep_blank_values=True)
    if not pairs:
        raise InitDataError("malformed", "initData не разбирается как query-string")
    out: dict[str, str] = {}
    for key, value in pairs:
        if key in out:
            raise InitDataError("malformed", f"параметр {key} встречается дважды")
        out[key] = value
    return out


def _parse_user(raw_user: str | None) -> MaxUser:
    if not raw_user:
        raise InitDataError("no_user", "в initData нет поля user")
    try:
        data: dict[str, Any] = json.loads(raw_user)
        return MaxUser(
            id=int(data["id"]),
            first_name=str(data.get("first_name") or ""),
            last_name=data.get("last_name") or None,
            username=data.get("username") or None,
            language_code=data.get("language_code") or None,
            photo_url=data.get("photo_url") or None,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise InitDataError("bad_user", "поле user не разбирается") from exc


def _parse_chat(raw_chat: str | None) -> MaxChat | None:
    if not raw_chat:
        return None
    try:
        data = json.loads(raw_chat)
        return MaxChat(id=int(data["id"]), type=str(data.get("type") or ""))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # Чат — необязательное поле; сломанный чат не должен ронять вход.
        return None


def validate_init_data(
    raw: str,
    bot_token: str,
    *,
    max_age_seconds: int,
    now: float | None = None,
) -> InitData:
    """Проверить подпись и свежесть, вернуть разобранные данные.

    Любая проблема — ``InitDataError`` с кодом: ``empty``, ``malformed``,
    ``missing_hash``, ``bad_signature``, ``expired``, ``no_user``, ``bad_user``.
    """
    if not bot_token:
        raise InitDataError("no_token", "MAX_BOT_TOKEN не задан")
    pairs = parse_pairs(raw)
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("missing_hash", "в initData нет hash")
    expected = sign(pairs, bot_token)
    if not hmac.compare_digest(expected, received_hash.lower()):
        raise InitDataError("bad_signature", "подпись initData не сходится")

    try:
        auth_date = int(pairs.get("auth_date", ""))
    except ValueError as exc:
        raise InitDataError("malformed", "auth_date не число") from exc
    current = time.time() if now is None else now
    if auth_date > current + _FUTURE_SKEW_SECONDS:
        raise InitDataError("expired", "auth_date из будущего")
    if max_age_seconds > 0 and current - auth_date > max_age_seconds:
        raise InitDataError("expired", "initData устарел")

    return InitData(
        user=_parse_user(pairs.get("user")),
        auth_date=auth_date,
        query_id=pairs.get("query_id") or None,
        start_param=pairs.get("start_param") or None,
        chat=_parse_chat(pairs.get("chat")),
    )


def build_init_data(params: dict[str, Any], bot_token: str) -> str:
    """Собрать подписанный initData (dev/тесты). Словари сериализуются в JSON как у MAX."""
    pairs: dict[str, str] = {}
    for key, value in params.items():
        if key == "hash":
            continue
        pairs[key] = (
            json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if isinstance(value, dict | list)
            else str(value)
        )
    pairs["hash"] = sign(pairs, bot_token)
    return urlencode(pairs)


def build_dev_init_data(
    bot_token: str,
    *,
    user_id: int,
    first_name: str = "Dev",
    last_name: str | None = "User",
    username: str | None = "dev",
    language_code: str = "ru",
    start_param: str | None = None,
    now: float | None = None,
) -> str:
    """initData тестового пользователя для запуска мини-аппа вне клиента MAX.

    Подписывается тем же токеном, что проверяет вход, поэтому ``/auth/max``
    проходит по-настоящему. Используется dev-ручкой API и CLI-скриптом.
    """
    issued = int(time.time() if now is None else now)
    user: dict[str, Any] = {"id": user_id, "first_name": first_name, "language_code": language_code}
    if last_name:
        user["last_name"] = last_name
    if username:
        user["username"] = username
    params: dict[str, Any] = {"query_id": f"dev-{issued}", "user": user, "auth_date": issued}
    if start_param:
        params["start_param"] = start_param
    return build_init_data(params, bot_token)
