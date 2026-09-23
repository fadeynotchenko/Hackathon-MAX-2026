"""Настройки файлового слоя: где лежат документы и чем конвертировать в PDF."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config.env import get_env_int, get_env_or_default


@dataclass(frozen=True)
class FilesConfig:
    documents_dir: Path
    soffice_bin: str
    pdf_timeout_seconds: int

    @classmethod
    def from_env(cls) -> FilesConfig:
        return cls(
            documents_dir=Path(get_env_or_default("DOCUMENTS_DIR", "app_data/documents")),
            soffice_bin=get_env_or_default("LIBREOFFICE_BIN", "soffice"),
            pdf_timeout_seconds=get_env_int("PDF_TIMEOUT_SECONDS", 60),
        )
