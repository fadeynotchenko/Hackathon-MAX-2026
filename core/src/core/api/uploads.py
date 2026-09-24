"""Приём файла сырым телом запроса: фото, скан или голосовое на распознавание.

Тело читается потоком с пределом: заголовку Content-Length верить нельзя, а
файл целиком держится в памяти. Тип файла здесь не проверяется — это дело
домена (``core.domain.media``), который смотрит на содержимое, а не на заголовки.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from core.domain.exceptions import AppError

IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff")
DOCUMENT_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
AUDIO_TYPES = ("audio/ogg", "audio/mpeg", "audio/mp4", "audio/webm", "audio/wav")


def binary_body(*media_types: str, description: str) -> dict[str, Any]:
    """``openapi_extra`` для ручки с файлом в теле: генератор TS-типов видит тело."""
    schema = {"type": "string", "format": "binary"}
    return {
        "requestBody": {
            "required": True,
            "description": description,
            "content": {
                media_type: {"schema": schema}
                for media_type in (*media_types, "application/octet-stream")
            },
        }
    }


def _too_large(max_bytes: int) -> AppError:
    return AppError(
        f"Файл больше {max_bytes // (1024 * 1024)} МБ, пришлите поменьше",
        code="media.too_large",
        status_code=413,
    )


async def read_body(request: Request, *, max_bytes: int) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise _too_large(max_bytes)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > max_bytes:
            raise _too_large(max_bytes)
    return bytes(data)
