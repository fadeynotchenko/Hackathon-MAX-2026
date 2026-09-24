"""Настройки файлового слоя: где лежат документы, чем конвертировать в PDF и какие
входящие файлы (фото, сканы, голосовые) принимаются на распознавание."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config.env import get_env_int, get_env_or_default

DEFAULT_MEDIA_MAX_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class FilesConfig:
    documents_dir: Path
    soffice_bin: str
    pdf_timeout_seconds: int
    # Входящий файл держится в памяти процесса целиком, поэтому лимит обязателен.
    media_max_bytes: int = DEFAULT_MEDIA_MAX_BYTES
    media_timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> FilesConfig:
        return cls(
            documents_dir=Path(get_env_or_default("DOCUMENTS_DIR", "app_data/documents")),
            soffice_bin=get_env_or_default("LIBREOFFICE_BIN", "soffice"),
            pdf_timeout_seconds=get_env_int("PDF_TIMEOUT_SECONDS", 60),
            media_max_bytes=get_env_int("MEDIA_MAX_BYTES", DEFAULT_MEDIA_MAX_BYTES),
            media_timeout_seconds=get_env_int("MEDIA_DOWNLOAD_TIMEOUT_SECONDS", 30),
        )
