"""Метаданные собранных файлов документа."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DocumentFile


class DocumentFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, document_id: int, fmt: str) -> DocumentFile | None:
        stmt = select(DocumentFile).where(
            DocumentFile.document_id == document_id, DocumentFile.format == fmt
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_document(self, document_id: int) -> list[DocumentFile]:
        stmt = (
            select(DocumentFile)
            .where(DocumentFile.document_id == document_id)
            .order_by(DocumentFile.format)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def upsert(
        self,
        *,
        document_id: int,
        fmt: str,
        filename: str,
        path: str,
        size: int,
        sha256: str,
        source_sha256: str,
    ) -> DocumentFile:
        """Актуальный файл один на формат: пересборка заменяет запись, а не копит версии."""
        record = await self.get(document_id, fmt)
        if record is None:
            record = DocumentFile(document_id=document_id, format=fmt)
            self._session.add(record)
        record.filename = filename
        record.path = path
        record.size = size
        record.sha256 = sha256
        record.source_sha256 = source_sha256
        await self._session.flush()
        await self._session.refresh(record, ["created_at", "updated_at"])
        return record
