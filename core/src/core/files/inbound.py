"""Скачивание вложений, присланных боту: фото, сканов, голосовых.

Ссылку на файл даёт MAX в апдейте сообщения, бот передаёт её ядру событием, а
байты ядро забирает само: стрим событий — не файловое хранилище. Размер
ограничен и до скачивания, и во время него — заголовку Content-Length верить
нельзя, а файл целиком держится в памяти процесса.

Хранилище MAX может быть подписано корнем НУЦ Минцифры, поэтому доверяем ему
вместе с публичными корнями — как и адаптер GigaChat.
"""

from __future__ import annotations

import ssl
from functools import lru_cache
from pathlib import Path

import certifi
import httpx

from core.files.errors import InboundFileError, InboundFileTooLargeError

CORE_ROOT = Path(__file__).resolve().parents[3]
RUSSIAN_ROOT_CA = CORE_ROOT / "certs" / "russian_trusted_root_ca.pem"
# Фото и сканы отдаём модели как есть: просим у хранилища JPEG/PNG, а не WEBP.
ACCEPT = "image/jpeg,image/png;q=0.9,application/pdf;q=0.9,audio/*;q=0.9,*/*;q=0.5"


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    if RUSSIAN_ROOT_CA.exists():
        context.load_verify_locations(cafile=str(RUSSIAN_ROOT_CA))
    return context


async def fetch_media(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    if not url.startswith("https://"):
        raise InboundFileError("вложение принимается только по https")
    verify: ssl.SSLContext | bool = True if transport is not None else _ssl_context()
    try:
        async with (
            httpx.AsyncClient(
                timeout=timeout_seconds, transport=transport, verify=verify, follow_redirects=True
            ) as client,
            client.stream("GET", url, headers={"Accept": ACCEPT}) as response,
        ):
            if response.status_code != 200:
                raise InboundFileError(f"хранилище ответило {response.status_code}")
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                raise InboundFileTooLargeError(f"вложение {declared} байт больше {max_bytes}")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise InboundFileTooLargeError(f"вложение больше {max_bytes} байт")
    except httpx.HTTPError as exc:
        raise InboundFileError(f"вложение не скачалось: {exc}") from exc
    return bytes(data)
