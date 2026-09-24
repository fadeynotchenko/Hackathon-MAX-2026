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
)
from .inbound import fetch_media
from .pdf import convert_to_pdf
from .storage import DocumentStorage, StoredFile

__all__ = [
    "DocumentStorage",
    "FileRenderError",
    "FilesConfig",
    "InboundFileError",
    "InboundFileTooLargeError",
    "PdfUnavailableError",
    "StoredFile",
    "build_docx",
    "convert_to_pdf",
    "fetch_media",
]
