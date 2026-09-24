"""Адаптер GigaChat: OAuth по ключу авторизации, chat/completions и хранилище файлов.

Токен доступа живёт 30 минут; держим его в памяти процесса и обновляем заранее.
Если API всё же ответил 401 (токен отозвали или часы разошлись), берём новый
токен и повторяем запрос ровно один раз — второй 401 значит, что не пускают
по ключу, и крутить дальше бессмысленно.

Вложения (фото, сканы, голосовые) модель читает только из хранилища GigaChat:
файл загружается в ``/files``, в сообщении передаётся его id, а после ответа
файл удаляется. Изображение — сырьё, а не документ: у провайдера оно живёт
ровно один запрос, у нас не хранится вовсе.

Лимит одновременных запросов у GigaChat жёсткий (на тарифе физлиц — один поток,
второй параллельный получает 429). Поэтому запросы к модели внутри процесса идут
очередью по ``max_concurrency``, а 429 — например, от соседнего воркера uvicorn —
переигрывается с паузой: пользователь ждёт пару секунд вместо «помощник не отвечает».

Структурированный ответ — через вызов функции, а не ``response_format``: в режиме
строгой JSON-схемы GigaChat-2-Max вставлял в объект мусорные токены
(``erv "seller_director"``, ``"E85000"``) и ломал JSON в большинстве ответов,
а аргументы принудительно вызванной функции приходят целым объектом.

Цепочка сертификатов: OAuth-хост Сбера подписан корнем НУЦ Минцифры, которого
нет в стандартных хранилищах, а хост API может быть и на публичном корне.
Поэтому доверяем обоим: certifi плюс корень Минцифры из ``core/certs``.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import certifi
import httpx

from core.llm.client import (
    Attachment,
    ChatMessage,
    LLMError,
    LLMInputError,
    LLMUnavailableError,
)
from core.llm.config import GigaChatConfig
from core.logs import biz_warn

logger = logging.getLogger(__name__)

# Обновляем токен за минуту до истечения, чтобы не отдать протухший в полёте.
TOKEN_REFRESH_MARGIN_SECONDS = 60
# Удаление файла — уборка после ответа: пользователь не должен ждать её дольше пары секунд.
FILE_DELETE_TIMEOUT_SECONDS = 5
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
# Повторы на 429: паузы 0,5 + 1 + 2 с укладываются в таймаут запроса к api.
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BACKOFF_SECONDS = 0.5
# Единственная функция, которую модель обязана вызвать: её аргументы и есть ответ.
ANSWER_FUNCTION = "submit_answer"


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
        self._slots = asyncio.Semaphore(cfg.max_concurrency)

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

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Запрос к API под токеном доступа; временные отказы — LLMUnavailableError."""
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            response = await self._authorized(method, path, **kwargs)
            if response.status_code != 429 or attempt == RATE_LIMIT_RETRIES:
                break
            await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS * 2**attempt)
        if response.status_code in _RETRYABLE_STATUSES:
            raise LLMUnavailableError(f"GigaChat ответил {response.status_code}")
        return response

    async def _authorized(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Один запрос с повтором на 401: токен могли отозвать раньше срока."""
        for attempt in range(2):
            token = await self._access_token(force=attempt > 0)
            try:
                response = await self._http.request(
                    method,
                    f"{self._cfg.api_url}{path}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    **kwargs,
                )
            except httpx.HTTPError as exc:
                raise LLMUnavailableError(f"GigaChat недоступен: {exc}") from exc
            if response.status_code != 401:
                return response
        raise LLMUnavailableError("GigaChat не принял обновлённый токен")

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._send("POST", "/chat/completions", json=payload)
        if response.status_code != 200:
            raise LLMError(f"GigaChat ответил {response.status_code}: {response.text[:300]}")
        try:
            message = response.json()["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("ответ GigaChat без сообщения") from exc
        if not isinstance(message, dict):
            raise LLMError("ответ GigaChat без сообщения")
        return message

    async def _upload(self, attachment: Attachment) -> str:
        response = await self._send(
            "POST",
            "/files",
            files={"file": (attachment.filename, attachment.data, attachment.media_type)},
            data={"purpose": "general"},
        )
        if response.status_code != 200:
            raise LLMInputError(
                f"GigaChat не принял файл {attachment.media_type}: "
                f"{response.status_code} {response.text[:300]}"
            )
        try:
            return str(response.json()["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMError("ответ GigaChat на загрузку файла без id") from exc

    async def _forget(self, file_ids: Sequence[str]) -> None:
        """Удалить загруженные файлы. Ошибка уборки не должна ронять ответ пользователю:
        её видно в логе, а файл без ссылок провайдер хранит в пределах своей квоты."""
        for file_id in file_ids:
            try:
                await asyncio.wait_for(
                    # Тело — как у официального SDK: multipart с id файла.
                    self._send("POST", f"/files/{file_id}/delete", files={"file": file_id}),
                    timeout=FILE_DELETE_TIMEOUT_SECONDS,
                )
            except (LLMError, TimeoutError) as exc:
                biz_warn(logger, "llm.file.delete_failed", file_id=file_id, error=str(exc))

    async def _wire_messages(
        self, messages: Sequence[ChatMessage], uploaded: list[str]
    ) -> list[dict[str, Any]]:
        """Сообщения в формате API. Id загруженных файлов копятся в ``uploaded``
        по мере загрузки: если упадёт второй файл, первый всё равно удалится."""
        wire: list[dict[str, Any]] = []
        for message in messages:
            item: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.attachments:
                ids = []
                for attachment in message.attachments:
                    file_id = await self._upload(attachment)
                    uploaded.append(file_id)
                    ids.append(file_id)
                item["attachments"] = ids
            wire.append(item)
        return wire

    async def _complete(self, messages: Sequence[ChatMessage], **extra: Any) -> dict[str, Any]:
        # Слот держится на всю цепочку «загрузить файл → ответ → удалить файл»:
        # чужой запрос не вклинится между загрузкой и ответом, и файл не пролежит
        # у провайдера дольше одного запроса.
        async with self._slots:
            uploaded: list[str] = []
            try:
                wire = await self._wire_messages(messages, uploaded)
                return await self._chat(
                    {
                        "model": self._cfg.model,
                        "messages": wire,
                        **{k: v for k, v in extra.items() if v is not None},
                    }
                )
            finally:
                await self._forget(uploaded)

    async def complete(
        self, messages: Sequence[ChatMessage], *, max_tokens: int | None = None
    ) -> str:
        message = await self._complete(messages, max_tokens=max_tokens)
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMError("ответ GigaChat без текста сообщения")
        return content

    async def complete_json(
        self, messages: Sequence[ChatMessage], *, schema: Mapping[str, Any]
    ) -> dict[str, Any]:
        message = await self._complete(
            messages,
            functions=[
                {
                    "name": ANSWER_FUNCTION,
                    "description": "Передать ответ в заданной структуре",
                    "parameters": dict(schema),
                }
            ],
            function_call={"name": ANSWER_FUNCTION},
            temperature=0.0,
        )
        call = message.get("function_call")
        arguments = call.get("arguments") if isinstance(call, dict) else None
        if not isinstance(arguments, dict):
            raise LLMError("GigaChat не вызвал функцию ответа")
        return arguments
