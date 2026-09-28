"""Предпросмотр листами: шаблон и документ такими, какими их получит контрагент.

Текстовый предпросмотр не показывал таблицы, линии и шрифты бланка, и казалось,
что оформление потеряно. Здесь лист — картинка страницы того же PDF, что уходит
в чат: у шаблона — пустой бланк, у документа — с текущими значениями и линиями
на месте пустых полей. Без LibreOffice (локальный стенд) — 503, и мини-апп
показывает прежний текстовый лист.
"""

from __future__ import annotations

from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.exceptions import AppError, NotFoundError
from core.files import FilesConfig, PdfUnavailableError, PreviewCache, PreviewPage, convert_to_pdf
from core.usecases.documents.drafts import get_document
from core.usecases.documents.files import template_source
from core.usecases.documents.templates import get_template


async def _same(pdf: bytes) -> bytes:
    return pdf


async def _page(
    source: tuple[bytes, bool], *, page: int, size: str, cfg: FilesConfig
) -> PreviewPage:
    data, is_pdf = source
    cache = PreviewCache(cfg.documents_dir, timeout_seconds=cfg.pdf_timeout_seconds)
    # Документ по PDF-образцу — уже PDF: LibreOffice ему не нужен.
    to_pdf = (
        _same
        if is_pdf
        else partial(
            convert_to_pdf, soffice_bin=cfg.soffice_bin, timeout_seconds=cfg.pdf_timeout_seconds
        )
    )
    try:
        found = await cache.page(data, size=size, page=page, to_pdf=to_pdf)
    except PdfUnavailableError as exc:
        raise AppError(
            "Предпросмотр листом сейчас недоступен",
            code="preview.unavailable",
            status_code=503,
            log_message=str(exc),
        ) from exc
    if found is None:
        raise NotFoundError("Такой страницы нет", code="preview.page_not_found")
    return found


async def template_preview(
    session: AsyncSession, *, user_id: int, template_id: int, page: int, size: str, cfg: FilesConfig
) -> PreviewPage:
    template = await get_template(session, user_id=user_id, template_id=template_id)
    source = await template_source(
        session, template, {}, title=template.title, text=template.preview
    )
    return await _page(source, page=page, size=size, cfg=cfg)


async def document_preview(
    session: AsyncSession, *, user_id: int, document_id: int, page: int, size: str, cfg: FilesConfig
) -> PreviewPage:
    document = await get_document(session, user_id=user_id, document_id=document_id)
    source = await template_source(
        session, document.template, document.values, title=document.title, text=document.preview
    )
    return await _page(source, page=page, size=size, cfg=cfg)
