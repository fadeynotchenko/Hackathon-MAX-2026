"""Предпросмотр листами: кеш по содержимому, число страниц и честный отказ без конвертера."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldValue
from core.domain.exceptions import AppError, NotFoundError
from core.files import FilesConfig, PdfUnavailableError
from core.files import previews as file_previews
from core.usecases.documents import (
    create_draft,
    document_preview,
    ensure_builtin_templates,
    list_templates,
    previews,
    set_fields,
    template_preview,
)
from tests.usecases.test_documents import make_user


@pytest.fixture
def converter(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """LibreOffice и pdftoppm подменены: PDF — сам DOCX, у него две страницы."""
    calls: list[bytes] = []

    async def to_pdf(docx: bytes, **_: object) -> bytes:
        calls.append(docx)
        return b"%PDF" + docx[:16]

    async def to_jpeg(pdf: bytes, *, width: int, timeout_seconds: int) -> list[bytes]:
        return [f"{width}-1".encode(), f"{width}-2".encode()]

    monkeypatch.setattr(previews, "convert_to_pdf", to_pdf)
    monkeypatch.setattr(file_previews, "pdf_to_jpeg", to_jpeg)
    return calls


async def test_template_blank_is_converted_once(
    session: AsyncSession, files_config: FilesConfig, converter: list[bytes]
) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    invoice = (await list_templates(session, user_id=user_id, slug="invoice"))[0]

    first = await template_preview(
        session, user_id=user_id, template_id=invoice.id, page=1, size="thumb", cfg=files_config
    )
    second = await template_preview(
        session, user_id=user_id, template_id=invoice.id, page=2, size="page", cfg=files_config
    )

    assert (first.data, first.pages) == (b"480-1", 2)
    assert (second.data, second.page) == (b"1240-2", 2)
    assert len(converter) == 1, "PDF бланка собирается один раз на все размеры и страницы"
    with pytest.raises(NotFoundError):
        await template_preview(
            session, user_id=user_id, template_id=invoice.id, page=3, size="page", cfg=files_config
        )


async def test_document_preview_follows_the_values(
    session: AsyncSession, files_config: FilesConfig, converter: list[bytes]
) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    offer = (await list_templates(session, user_id=user_id, slug="offer"))[0]
    draft = await create_draft(session, user_id=user_id, template_id=offer.id)

    await document_preview(
        session, user_id=user_id, document_id=draft.id, page=1, size="page", cfg=files_config
    )
    await set_fields(
        session, user_id=user_id, document_id=draft.id, values={"total": FieldValue("150 000")}
    )
    await document_preview(
        session, user_id=user_id, document_id=draft.id, page=1, size="page", cfg=files_config
    )

    assert len(converter) == 2, "правка значения — новая редакция листа"


async def test_preview_without_converter_is_unavailable(
    session: AsyncSession, files_config: FilesConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def missing(docx: bytes, **_: object) -> bytes:
        raise PdfUnavailableError("конвертер 'soffice' не найден")

    monkeypatch.setattr(previews, "convert_to_pdf", missing)
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    invoice = (await list_templates(session, user_id=user_id, slug="invoice"))[0]

    with pytest.raises(AppError) as exc:
        await template_preview(
            session, user_id=user_id, template_id=invoice.id, page=1, size="page", cfg=files_config
        )
    assert (exc.value.code, exc.value.status_code) == ("preview.unavailable", 503)
