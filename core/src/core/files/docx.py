"""Сборка DOCX из готового текста документа.

Тело встроенных шаблонов — текст с подставленными значениями, поэтому DOCX
собирается программно: абзац на строку, моноширинного форматирования нет.
Когда появятся шаблоны-файлы компании, рядом встанет второй сборщик — он будет
подставлять значения в готовый .docx, сохраняя её оформление.
"""

from __future__ import annotations

from io import BytesIO

from docx import Document as DocxDocument
from docx.shared import Pt

BASE_FONT = "Times New Roman"
BASE_SIZE_PT = 12


def build_docx(title: str, text: str) -> bytes:
    document = DocxDocument()
    style = document.styles["Normal"]
    style.font.name = BASE_FONT
    style.font.size = Pt(BASE_SIZE_PT)

    if title:
        heading = document.add_paragraph()
        run = heading.add_run(title)
        run.bold = True
        run.font.size = Pt(BASE_SIZE_PT + 2)

    for line in text.splitlines():
        document.add_paragraph(line)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
