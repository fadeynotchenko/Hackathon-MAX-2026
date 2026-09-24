"""Тип входящего файла по сигнатуре и проверка перед распознаванием."""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from docx import Document as DocxDocument

from core.domain.exceptions import AppError
from core.domain.media import (
    AUDIBLE,
    BMP,
    DOCX,
    JPEG,
    M4A,
    MP3,
    OGG,
    PDF,
    PNG,
    READABLE,
    TIFF,
    WAV,
    WEBM,
    WEBP,
    MediaKind,
    require_media,
    sniff_media,
)


def _docx() -> bytes:
    buffer = BytesIO()
    DocxDocument().save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", JPEG),
        (b"\x89PNG\r\n\x1a\n\x00\x00", PNG),
        (b"RIFF\x24\x00\x00\x00WEBPVP8 ", WEBP),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", WAV),
        (b"II*\x00\x08\x00\x00\x00", TIFF),
        (b"BM" + b"\x00" * 40, BMP),
        (b"%PDF-1.7\n%\xe2\xe3", PDF),
        (b"OggS\x00\x02" + b"\x00" * 10, OGG),
        (b"\x00\x00\x00\x20ftypM4A \x00\x00", M4A),
        (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81", WEBM),
        (b"ID3\x04\x00\x00\x00\x00", MP3),
        (b"\xff\xfb\x90\x64\x00", MP3),
    ],
)
def test_signature_decides_the_type(data: bytes, expected) -> None:
    assert sniff_media(data) == expected


def test_docx_is_told_apart_from_other_zip_files() -> None:
    assert sniff_media(_docx()) == DOCX
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
    assert sniff_media(archive.getvalue()) is None, "XLSX тоже zip, но это не DOCX"


@pytest.mark.parametrize(
    "data",
    [b"", b"plain text", b"\xff\xf1\x50\x80", b"\xff\xfe\x00h\x00i", b"GIF89a\x01\x00"],
)
def test_unknown_or_lookalike_formats_are_not_guessed(data: bytes) -> None:
    """AAC в ADTS (FF F1) и UTF-16 с BOM (FF FE) похожи на кадр MP3 только первыми битами."""
    assert sniff_media(data) is None


def test_require_media_checks_kind_and_size() -> None:
    photo = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    assert require_media(photo, kinds=READABLE, max_bytes=1000) == JPEG
    assert JPEG.kind is MediaKind.IMAGE

    with pytest.raises(AppError) as too_large:
        require_media(photo, kinds=READABLE, max_bytes=50)
    assert (too_large.value.code, too_large.value.status_code) == ("media.too_large", 413)

    with pytest.raises(AppError) as wrong_kind:
        require_media(photo, kinds=AUDIBLE, max_bytes=1000)
    assert wrong_kind.value.code == "media.unsupported"
    assert "голосовое" in wrong_kind.value.public_message

    with pytest.raises(AppError) as empty:
        require_media(b"", kinds=READABLE, max_bytes=1000)
    assert empty.value.code == "media.empty"
