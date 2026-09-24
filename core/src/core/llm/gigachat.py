"""Адаптер GigaChat: OAuth по ключу авторизации и chat/completions.

Токен доступа живёт 30 минут; держим его в памяти процесса и обновляем заранее.
Если API всё же ответил 401 (токен отозвали или часы разошлись), берём новый
токен и повторяем запрос ровно один раз — второй 401 значит, что не пускают
по ключу, и крутить дальше бессмысленно.

Цепочка сертификатов: OAuth-хост Сбера подписан корнем НУЦ Минцифры, которого
нет в стандартных хранилищах, а хост API может быть и на публичном корне.
Поэтому доверяем обоим: certifi плюс корень Минцифры из ``core/certs``.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import certifi
import httpx

from core.llm.client import ChatMessage, LLMError, LLMUnavailableError
from core.llm.config import GigaChatConfig

# Обновляем токен за минуту до истечения, чтобы не отдать протухший в полёте.
TOKEN_REFRESH_MARGIN_SECONDS = 60
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


def _ssl_context(ca_bundle: Any) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=str(ca_bundle))
    return context


class GigaChatClient:
    def __init__(
        self, cfg: GigaChatConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._cfg = cfg
        self._http = httpx.AsyncClient(
            timeout=cfg.timeout_seconds,
            transport=transport,
            verify=True if transport is not None else _ssl_context(cfg.ca_bundle),
        )
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _access_token(self, *, force: bool = False) -> str:
        async with self._token_lock:
            fresh = time.time() < self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS
            if self._token is not None and fresh and not force:
                return self._token
            try:
                response = await self._http.post(
                    self._cfg.auth_url,
                    headers={
                        "Authorization": f"Basic {self._cfg.auth_key}",
                        "RqUID": str(uuid.uuid4()),
                        "Accept": "application/json",
                    },
                    data={"scope": self._cfg.scope},
                )
            except httpx.HTTPError as exc:
                raise LLMUnavailableError(f"GigaChat OAuth недоступен: {exc}") from exc
            if response.status_code != 200:
                raise LLMUnavailableError(f"GigaChat OAuth ответил {response.status_code}")
            body = response.json()
            self._token = str(body["access_token"])
            # expires_at приходит в миллисекундах эпохи.
            self._token_expires_at = float(body["expires_at"]) / 1000
            return self._token

    async def _chat(self, payload: dict[str, Any]) -> str:
        for attempt in range(2):
            token = await self._access_token(force=attempt > 0)
            try:
                response = await self._http.post(
                    f"{self._cfg.api_url}/chat/completions",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    json=payload,
                )
            except httpx.HTTPError as exc:
                raise LLMUnavailableError(f"GigaChat недоступен: {exc}") from exc
            if response.status_code == 401 and attempt == 0:
                continue
            if response.status_code in _RETRYABLE_STATUSES or response.status_code == 401:
                raise LLMUnavailableError(f"GigaChat ответил {response.status_code}")
            if response.status_code != 200:
                raise LLMError(f"GigaChat ответил {response.status_code}: {response.text[:300]}")
            try:
                return str(response.json()["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise LLMError("ответ GigaChat без текста сообщения") from exc
        raise LLMUnavailableError("GigaChat не принял обновлённый токен")

    def _payload(self, messages: Sequence[ChatMessage], **extra: Any) -> dict[str, Any]:
        return {
            "model": self._cfg.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            **{k: v for k, v in extra.items() if v is not None},
        }

    async def complete(
        self, messages: Sequence[ChatMessage], *, max_tokens: int | None = None
    ) -> str:
        return await self._chat(self._payload(messages, max_tokens=max_tokens))

    async def complete_json(
        self, messages: Sequence[ChatMessage], *, schema: Mapping[str, Any]
    ) -> dict[str, Any]:
        content = await self._chat(
            self._payload(
                messages,
                # Строгий JSON по схеме: модель не может вернуть поле, которого нет в шаблоне.
                response_format={"type": "json_schema", "schema": dict(schema), "strict": True},
                temperature=0.0,
            )
        )
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError("GigaChat вернул не JSON вместо значений полей") from exc
        if not isinstance(data, dict):
            raise LLMError("GigaChat вернул JSON не объектом")
        return data
