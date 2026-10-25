"""Текст PDF-образца для шаблона.

Оформление PDF в шаблон не переносится — из PDF не собрать редактируемый DOCX
того же вида, — поэтому шаблон из PDF становится текстовым: берутся строки
текстового слоя по страницам. У скана текстового слоя нет: о нём говорит
``ScannedPdfError``, и текст страниц читает помощник по картинкам
(``core.usecases.agent.template_import``) — человек сверяет его перед сохранением.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from core.files.errors import ScannedPdfError, TemplateFileError

# Больше страниц в образце делового документа не бывает; дальше — не бланк.
MAX_PAGES = 30


def pdf_lines(data: bytes) -> list[str]:
    try:
        reader = PdfReader(BytesIO(data))
        pages = reader.pages[:MAX_PAGES]
        text = "\n\n".join(page.extract_text() or "" for page in pages)
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise TemplateFileError(f"PDF не открылся: {exc}") from exc
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    if not any(line.strip() for line in lines):
        raise ScannedPdfError("в PDF нет текстового слоя")
    return lines
