"""Текст PDF-образца для шаблона.

Оформление PDF в шаблон не переносится — из PDF не собрать редактируемый DOCX
того же вида, — поэтому шаблон из PDF становится текстовым: берутся строки
текстового слоя по страницам. У скана текстового слоя нет, такой файл
отклоняется: распознавать бланк целиком по картинке значит додумывать текст.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from core.files.errors import TemplateFileError

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
        raise TemplateFileError("в PDF нет текстового слоя")
    return lines
