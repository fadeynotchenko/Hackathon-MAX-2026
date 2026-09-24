"""Входящие файлы: что за файл и годится ли он для распознавания.

Тип определяется по первым байтам, а не по заголовку или расширению: их задаёт
клиент (мини-апп, MAX, пересланный файл), а модели важно, что внутри. Файл,
который выдаёт себя за фото, отсекается здесь, до обращения к провайдеру.
"""

from __future__ import annotations

import zipfile
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO

from core.domain.exceptions import AppError


class MediaKind(StrEnum):
    IMAGE = "image"  # фото, скриншот, скан картинкой
    DOCUMENT = "document"  # PDF, DOCX
    AUDIO = "audio"  # голосовое


@dataclass(frozen=True)
class MediaType:
    mime: str
    extension: str
    kind: MediaKind
    title: str


JPEG = MediaType("image/jpeg", "jpg", MediaKind.IMAGE, "JPG")
PNG = MediaType("image/png", "png", MediaKind.IMAGE, "PNG")
WEBP = MediaType("image/webp", "webp", MediaKind.IMAGE, "WEBP")
BMP = MediaType("image/bmp", "bmp", MediaKind.IMAGE, "BMP")
TIFF = MediaType("image/tiff", "tiff", MediaKind.IMAGE, "TIFF")
PDF = MediaType("application/pdf", "pdf", MediaKind.DOCUMENT, "PDF")
DOCX = MediaType(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "docx",
    MediaKind.DOCUMENT,
    "DOCX",
)
OGG = MediaType("audio/ogg", "ogg", MediaKind.AUDIO, "OGG")
MP3 = MediaType("audio/mpeg", "mp3", MediaKind.AUDIO, "MP3")
M4A = MediaType("audio/mp4", "m4a", MediaKind.AUDIO, "M4A")
WAV = MediaType("audio/wav", "wav", MediaKind.AUDIO, "WAV")
WEBM = MediaType("audio/webm", "weba", MediaKind.AUDIO, "WEBM")

READABLE = frozenset({MediaKind.IMAGE, MediaKind.DOCUMENT})
AUDIBLE = frozenset({MediaKind.AUDIO})

_HINTS = {
    MediaKind.IMAGE: "фото JPG или PNG",
    MediaKind.DOCUMENT: "файл PDF или DOCX",
    MediaKind.AUDIO: "голосовое сообщение",
}


def _is_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except (zipfile.BadZipFile, ValueError):
        return False


def sniff_media(data: bytes) -> MediaType | None:
    """Тип файла по сигнатуре; ``None`` — формат, который распознавание не читает."""
    head = data[:16]
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return WEBP
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return WAV
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return TIFF
    if head.startswith(b"BM") and len(data) > 26:
        return BMP
    if b"%PDF-" in data[:1024]:
        return PDF
    if head.startswith(b"PK\x03\x04"):
        return DOCX if _is_docx(data) else None
    if head.startswith(b"OggS"):
        return OGG
    if head[4:8] == b"ftyp":
        return M4A
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return WEBM
    if head.startswith(b"ID3") or _mp3_frame(head):
        return MP3
    return None


def _mp3_frame(head: bytes) -> bool:
    """Заголовок кадра MPEG Layer III: 11 бит синхронизации и биты слоя «01».
    Без проверки слоя сюда попали бы AAC в ADTS и UTF-16 с BOM (FF FE)."""
    return len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0 and head[1] & 0x06 == 0x02


def require_media(data: bytes, *, kinds: Collection[MediaKind], max_bytes: int) -> MediaType:
    """Проверить файл перед распознаванием: не пустой, не больше лимита, читаемого вида."""
    if not data:
        raise AppError("Файл пустой", code="media.empty", status_code=422)
    if len(data) > max_bytes:
        limit_mb = max_bytes / 1024 / 1024
        raise AppError(
            f"Файл больше {limit_mb:.0f} МБ, пришлите поменьше",
            code="media.too_large",
            status_code=413,
        )
    media = sniff_media(data)
    if media is None or media.kind not in kinds:
        wanted = ", ".join(_HINTS[kind] for kind in MediaKind if kind in kinds)
        raise AppError(
            f"Такой файл не прочитать. Подойдёт {wanted}",
            code="media.unsupported",
            status_code=415,
        )
    return media
