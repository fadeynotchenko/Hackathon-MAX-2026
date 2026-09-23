"""Одноразовые токены на скачивание файла документа (Redis).

Бот не ходит в API под пользователем: JWT мини-аппа ему не принадлежит, а
сервисный пароль пришлось бы хранить в двух местах. Вместо этого ядро кладёт в
событие короткоживущий токен, а файл отдаёт ручка без авторизации: токен
непредсказуем, живёт час и сгорает при первом использовании (GETDEL).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass

from redis.asyncio import Redis

KEY_PREFIX = "documents:download:"
DEFAULT_TTL_SECONDS = 3600


@dataclass(frozen=True)
class DownloadTicket:
    document_id: int
    user_id: int
    format: str


class DownloadTokenRepository:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def issue(self, ticket: DownloadTicket, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
        token = secrets.token_urlsafe(32)
        payload = json.dumps(
            {
                "document_id": ticket.document_id,
                "user_id": ticket.user_id,
                "format": ticket.format,
            }
        )
        await self._redis.set(f"{KEY_PREFIX}{token}", payload, ex=ttl_seconds)
        return token

    async def consume(self, token: str) -> DownloadTicket | None:
        raw = await self._redis.getdel(f"{KEY_PREFIX}{token}")
        if raw is None:
            return None
        data = json.loads(raw)
        return DownloadTicket(
            document_id=int(data["document_id"]),
            user_id=int(data["user_id"]),
            format=str(data["format"]),
        )
