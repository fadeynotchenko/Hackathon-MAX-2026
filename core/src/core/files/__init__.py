"""Файлы документов: сборка DOCX, конвертация в PDF, хранение на диске.

Инфраструктурный слой рядом с ``db`` и ``events``: сценарии знают про
«отрендерить и сохранить», но не про python-docx, LibreOffice и пути на диске.
"""

from .config import FilesConfig
from .docx import build_docx
from .errors import FileRenderError, PdfUnavailableError
from .pdf import convert_to_pdf
from .storage import DocumentStorage, StoredFile

__all__ = [
    "DocumentStorage",
    "FileRenderError",
    "FilesConfig",
    "PdfUnavailableError",
    "StoredFile",
    "build_docx",
    "convert_to_pdf",
]
