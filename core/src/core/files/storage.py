"""Хранение файлов документов на диске.

Объектного хранилища в стеке пока нет: файлы лежат в каталоге-томе, в базе —
относительный путь и хеш. Путь всегда строится сервисом, а при чтении
проверяется, что он не вывел за пределы корня: имя файла приходит из базы,
но дорога до диска не должна зависеть от того, что туда однажды записали.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredFile:
    relative_path: str
    size: int
    sha256: str


class DocumentStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, *, document_id: int, extension: str, data: bytes) -> StoredFile:
        digest = hashlib.sha256(data).hexdigest()
        relative = f"{document_id}/{digest[:16]}.{extension}"
        target = self._resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return StoredFile(relative_path=relative, size=len(data), sha256=digest)

    def read(self, relative_path: str) -> bytes:
        return self._resolve(relative_path).read_bytes()

    def exists(self, relative_path: str) -> bool:
        try:
            return self._resolve(relative_path).is_file()
        except ValueError:
            return False

    def _resolve(self, relative_path: str) -> Path:
        root = self._root.resolve()
        target = (root / relative_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"путь {relative_path!r} выходит за пределы хранилища")
        return target
