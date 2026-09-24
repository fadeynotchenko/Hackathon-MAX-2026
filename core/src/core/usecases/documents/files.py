"""Сборка и выдача файла документа.

Файл собирается только из проверенного документа: пока есть ошибки, пустые
обязательные поля или неподтверждённые распознанные значения, рендер отказывает.
Готовый файл помнит хеш текста, из которого собран, — после правки полей он
помечается устаревшим, чтобы контрагенту не ушла прошлая редакция.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DocumentFile
from core.db.repositories import DocumentFileRepository, DownloadTicket, DownloadTokenRepository
from core.domain.exceptions import AppError, ConflictError, NotFoundError
from core.events import DocumentReady, EventBus
from core.files import DocumentStorage, FilesConfig, PdfUnavailableError, build_docx, convert_to_pdf
from core.usecases.documents.drafts import DocumentView, get_document

DOCX = "docx"
PDF = "pdf"
MEDIA_TYPES = {
    DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    PDF: "application/pdf",
}
_UNSAFE_IN_NAME = re.compile(r"[^\w\s.()№-]+", re.UNICODE)


@dataclass(frozen=True)
class DocumentFileView:
    format: str
    filename: str
    size: int
    sha256: str
    stale: bool
    created_at: datetime
    updated_at: datetime


def source_hash(document: DocumentView) -> str:
    return hashlib.sha256(f"{document.title}\n{document.preview}".encode()).hexdigest()


def to_view(record: DocumentFile, *, current_source: str) -> DocumentFileView:
    return DocumentFileView(
        format=record.format,
        filename=record.filename,
        size=record.size,
        sha256=record.sha256,
        stale=record.source_sha256 != current_source,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def build_filename(title: str, fmt: str) -> str:
    cleaned = _UNSAFE_IN_NAME.sub("", title).strip() or "document"
    return f"{cleaned[:100]}.{fmt}"


async def list_document_files(
    session: AsyncSession, *, user_id: int, document_id: int
) -> list[DocumentFileView]:
    document = await get_document(session, user_id=user_id, document_id=document_id)
    current = source_hash(document)
    records = await DocumentFileRepository(session).list_for_document(document_id)
    return [to_view(record, current_source=current) for record in records]


async def render_document(
    session: AsyncSession, *, user_id: int, document_id: int, fmt: str, cfg: FilesConfig
) -> DocumentFileView:
    if fmt not in MEDIA_TYPES:
        raise NotFoundError(f"Формат {fmt} не поддерживается", code="document.format_unknown")
    document = await get_document(session, user_id=user_id, document_id=document_id)
    if not document.ready:
        raise ConflictError(
            "Документ ещё не готов: остались пустые или непроверенные поля",
            code="document.not_ready",
        )

    docx_bytes = build_docx(document.title, document.preview)
    if fmt == PDF:
        try:
            data = await convert_to_pdf(
                docx_bytes,
                soffice_bin=cfg.soffice_bin,
                timeout_seconds=cfg.pdf_timeout_seconds,
            )
        except PdfUnavailableError as exc:
            raise AppError(
                "PDF сейчас собрать нечем, DOCX доступен",
                code="render.pdf_unavailable",
                status_code=503,
                log_message=str(exc),
            ) from exc
    else:
        data = docx_bytes

    stored = DocumentStorage(cfg.documents_dir).save(
        document_id=document_id, extension=fmt, data=data
    )
    record = await DocumentFileRepository(session).upsert(
        document_id=document_id,
        fmt=fmt,
        filename=build_filename(document.title, fmt),
        path=stored.relative_path,
        size=stored.size,
        sha256=stored.sha256,
        source_sha256=source_hash(document),
    )
    return to_view(record, current_source=source_hash(document))


async def load_document_file(
    session: AsyncSession, *, user_id: int, document_id: int, fmt: str, cfg: FilesConfig
) -> tuple[DocumentFileView, bytes]:
    document = await get_document(session, user_id=user_id, document_id=document_id)
    record = await DocumentFileRepository(session).get(document_id, fmt)
    storage = DocumentStorage(cfg.documents_dir)
    if record is None or not storage.exists(record.path):
        raise NotFoundError("Файл не собран", code="document.file_not_found")
    return to_view(record, current_source=source_hash(document)), storage.read(record.path)


async def send_document_to_chat(
    session: AsyncSession,
    *,
    user_id: int,
    max_user_id: int,
    document_id: int,
    fmt: str,
    cfg: FilesConfig,
    bus: EventBus,
    tokens: DownloadTokenRepository,
    text: str | None = None,
) -> tuple[DocumentFileView, str]:
    """Собрать файл при необходимости и поставить событие на доставку ботом.

    Пересборка происходит, если файла нет или он устарел: иначе пользователь
    получил бы в чат прошлую редакцию документа, выглядящую как свежая.
    """
    document = await get_document(session, user_id=user_id, document_id=document_id)
    files = {
        f.format: f
        for f in await list_document_files(session, user_id=user_id, document_id=document_id)
    }
    file = files.get(fmt)
    if file is None or file.stale:
        file = await render_document(
            session, user_id=user_id, document_id=document_id, fmt=fmt, cfg=cfg
        )

    token = await tokens.issue(DownloadTicket(document_id=document_id, user_id=user_id, format=fmt))
    event_id = await bus.document_ready(
        DocumentReady(
            max_user_id=max_user_id,
            document_id=document_id,
            title=document.title,
            filename=file.filename,
            format=fmt,  # type: ignore[arg-type]
            size=file.size,
            download_token=token,
            # Свой текст приходит от человека (или письмо помощника, которое он
            # просмотрел); без него — служебная строка, а не молчаливая генерация.
            text=(text or "").strip()
            or f"{document.title}: файл во вложении. Проверьте реквизиты перед отправкой.",
        )
    )
    return file, event_id


async def load_file_by_token(
    session: AsyncSession, *, token: str, cfg: FilesConfig, tokens: DownloadTokenRepository
) -> tuple[str, str, bytes]:
    """Отдать файл по одноразовому токену: возвращает имя, формат и байты."""
    ticket = await tokens.consume(token)
    if ticket is None:
        raise NotFoundError("Ссылка истекла или уже использована", code="document.token_invalid")
    file, data = await load_document_file(
        session,
        user_id=ticket.user_id,
        document_id=ticket.document_id,
        fmt=ticket.format,
        cfg=cfg,
    )
    return file.filename, file.format, data
