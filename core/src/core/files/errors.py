"""Ошибки файлового слоя. В HTTP их переводят сценарии: слой не знает про статусы."""

from __future__ import annotations


class FileRenderError(RuntimeError):
    """Файл собрать не удалось."""


class PdfUnavailableError(FileRenderError):
    """LibreOffice не установлен или не отозвался: PDF временно недоступен."""


class InboundFileError(RuntimeError):
    """Вложение, присланное боту, не скачалось: ссылка протухла, хранилище не ответило."""


class InboundFileTooLargeError(InboundFileError):
    """Вложение больше лимита на распознавание: дальше качать бессмысленно."""
