"""Файлы: сборка DOCX, конвертация в PDF, хранение на диске, скачивание вложений.

Инфраструктурный слой рядом с ``db`` и ``events``: сценарии знают про
«отрендерить и сохранить» и «получить присланное фото», но не про python-docx,
LibreOffice, пути на диске и HTTP до хранилища MAX.
"""

from .config import FilesConfig
from .docx import build_docx
from .errors import (
    FileRenderError,
    InboundFileError,
    InboundFileTooLargeError,
    PdfUnavailableError,
    TemplateFileError,
)
from .inbound import fetch_media
from .pdf import convert_to_pdf
from .pdf_overlay import fill_pdf
from .pdf_text import pdf_lines
from .previews import PREVIEW_WIDTHS, PreviewCache, PreviewPage
from .storage import DocumentStorage, StoredFile
from .template_docx import docx_layout, docx_lines, fill_docx, mark_blank_cells

__all__ = [
    "PREVIEW_WIDTHS",
    "DocumentStorage",
    "FileRenderError",
    "FilesConfig",
    "InboundFileError",
    "InboundFileTooLargeError",
    "PdfUnavailableError",
    "PreviewCache",
    "PreviewPage",
    "StoredFile",
    "TemplateFileError",
    "build_docx",
    "convert_to_pdf",
    "docx_layout",
    "docx_lines",
    "fetch_media",
    "fill_docx",
    "fill_pdf",
    "mark_blank_cells",
    "pdf_lines",
]
