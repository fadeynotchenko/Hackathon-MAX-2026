"""Сборка файла документа: готовность, устаревание, недоступный PDF, границы хранилища."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldValue, ValueSource
from core.domain.exceptions import AppError, ConflictError, NotFoundError
from core.files import DocumentStorage, FilesConfig
from core.usecases.documents import (
    DOCX,
    PDF,
    create_draft,
    ensure_builtin_templates,
    list_document_files,
    list_templates,
    load_document_file,
    render_document,
    set_fields,
)
from tests.usecases.test_documents import make_user

READY_OFFER = {
    "date": FieldValue("23.09.2026"),
    "seller_name": FieldValue("ООО «Ромашка»"),
    "client_name": FieldValue("ООО «Клиент»"),
    "subject": FieldValue("Разработка мини-приложения"),
    "scope": FieldValue("Бэкенд, бот, мини-апп"),
    "total": FieldValue("450 000"),
    "valid_until": FieldValue("31.10.2026"),
}


async def _ready_document(session: AsyncSession, user_id: int) -> int:
    await ensure_builtin_templates(session)
    offer = next(t for t in await list_templates(session, user_id=user_id) if t.slug == "offer")
    draft = await create_draft(session, user_id=user_id, template_id=offer.id)
    filled = await set_fields(
        session, user_id=user_id, document_id=draft.id, values=READY_OFFER, title="КП для «Клиента»"
    )
    assert filled.ready
    return draft.id


def _docx_text(data: bytes) -> str:
    return "\n".join(p.text for p in DocxDocument(BytesIO(data)).paragraphs)


async def test_render_docx_contains_filled_values(
    session: AsyncSession, files_config: FilesConfig
) -> None:
    user_id = await make_user(session)
    document_id = await _ready_document(session, user_id)

    file = await render_document(
        session, user_id=user_id, document_id=document_id, fmt=DOCX, cfg=files_config
    )

    assert file.format == DOCX and file.size > 0 and file.stale is False
    # Кавычки-ёлочки и прочая типографика из имени файла вычищаются.
    assert file.filename == "КП для Клиента.docx"
    _, data = await load_document_file(
        session, user_id=user_id, document_id=document_id, fmt=DOCX, cfg=files_config
    )
    text = _docx_text(data)
    assert "КП для «Клиента»" in text
    assert "450 000,00" in text
    assert "ООО «Клиент»" in text


READY_INVOICE = {
    "number": FieldValue("17"),
    "seller_name": FieldValue("ООО «Ромашка»"),
    "seller_inn": FieldValue("7707083893"),
    "seller_bank": FieldValue("ПАО Сбербанк"),
    "seller_bic": FieldValue("044525225"),
    "seller_account": FieldValue("40702810438000123459"),
    "client_name": FieldValue("ООО «Клиент»"),
    "item": FieldValue("Разработка сайта"),
    "total": FieldValue("120 000"),
}


async def test_invoice_file_is_named_by_number_and_has_one_heading(
    session: AsyncSession, files_config: FilesConfig
) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    (invoice,) = await list_templates(session, user_id=user_id, slug="invoice")
    draft = await create_draft(session, user_id=user_id, template_id=invoice.id)
    filled = await set_fields(session, user_id=user_id, document_id=draft.id, values=READY_INVOICE)
    assert filled.ready, filled.missing

    file = await render_document(
        session, user_id=user_id, document_id=draft.id, fmt=DOCX, cfg=files_config
    )
    assert file.filename == "Счёт на оплату № 17.docx", "счета в чате различаются номером"
    _, data = await load_document_file(
        session, user_id=user_id, document_id=draft.id, fmt=DOCX, cfg=files_config
    )
    paragraphs = [p for p in DocxDocument(BytesIO(data)).paragraphs if p.text.strip()]
    assert paragraphs[0].text.startswith("Счёт на оплату № 17 от "), "заголовок — первая строка"
    assert paragraphs[0].runs[0].bold
    assert not any(p.text == "Счёт на оплату" for p in paragraphs), "название не повторяется"


async def test_draft_cannot_be_rendered(session: AsyncSession, files_config: FilesConfig) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    offer = next(t for t in await list_templates(session, user_id=user_id) if t.slug == "offer")
    draft = await create_draft(session, user_id=user_id, template_id=offer.id)

    with pytest.raises(ConflictError) as exc:
        await render_document(
            session, user_id=user_id, document_id=draft.id, fmt=DOCX, cfg=files_config
        )
    assert exc.value.code == "document.not_ready"


async def test_file_goes_stale_after_editing_fields(
    session: AsyncSession, files_config: FilesConfig
) -> None:
    user_id = await make_user(session)
    document_id = await _ready_document(session, user_id)
    await render_document(
        session, user_id=user_id, document_id=document_id, fmt=DOCX, cfg=files_config
    )

    await set_fields(
        session,
        user_id=user_id,
        document_id=document_id,
        values={"total": FieldValue("500 000")},
    )
    files = await list_document_files(session, user_id=user_id, document_id=document_id)
    assert [f.stale for f in files] == [True], "файл собран до правки суммы"

    await render_document(
        session, user_id=user_id, document_id=document_id, fmt=DOCX, cfg=files_config
    )
    files = await list_document_files(session, user_id=user_id, document_id=document_id)
    assert [f.stale for f in files] == [False]


async def test_missing_file_is_not_found(session: AsyncSession, files_config: FilesConfig) -> None:
    user_id = await make_user(session)
    document_id = await _ready_document(session, user_id)
    with pytest.raises(NotFoundError) as exc:
        await load_document_file(
            session, user_id=user_id, document_id=document_id, fmt=DOCX, cfg=files_config
        )
    assert exc.value.code == "document.file_not_found"


async def test_pdf_without_converter_says_so(
    session: AsyncSession, files_config: FilesConfig
) -> None:
    user_id = await make_user(session)
    document_id = await _ready_document(session, user_id)
    cfg = FilesConfig(
        documents_dir=files_config.documents_dir,
        soffice_bin="maxapp-no-such-converter",
        pdf_timeout_seconds=5,
    )

    with pytest.raises(AppError) as exc:
        await render_document(session, user_id=user_id, document_id=document_id, fmt=PDF, cfg=cfg)
    assert exc.value.code == "render.pdf_unavailable" and exc.value.status_code == 503


def test_storage_refuses_to_leave_its_root(tmp_path: Path) -> None:
    storage = DocumentStorage(tmp_path / "documents")
    stored = storage.save(document_id=7, extension="docx", data=b"PK\x03\x04")
    assert storage.read(stored.relative_path) == b"PK\x03\x04"
    assert storage.exists(stored.relative_path)
    assert not storage.exists("../../etc/passwd")
    with pytest.raises(ValueError, match="выходит за пределы"):
        storage.read("../../etc/passwd")


async def test_send_rebuilds_a_file_missing_on_disk(
    session: AsyncSession, redis, files_config: FilesConfig
) -> None:
    """Запись о файле без самого файла (база из бэкапа, файлы — нет): отправка
    пересобирает его, а не отдаёт боту токен на 404."""
    from core.db.repositories import DocumentFileRepository, DownloadTokenRepository
    from core.events import EventBus
    from core.usecases.documents import document_history, send_document_to_chat

    user_id = await make_user(session, max_user_id=77)
    document_id = await _ready_document(session, user_id)
    await render_document(
        session, user_id=user_id, document_id=document_id, fmt=DOCX, cfg=files_config
    )
    row = await DocumentFileRepository(session).get(document_id, DOCX)
    assert row is not None
    storage = DocumentStorage(files_config.documents_dir)
    bus = EventBus(redis, stream_to_bot="test:to_bot", source="test", maxlen=100)
    tokens = DownloadTokenRepository(redis)

    async def send() -> None:
        await send_document_to_chat(
            session,
            user_id=user_id,
            max_user_id=77,
            document_id=document_id,
            fmt=DOCX,
            cfg=files_config,
            bus=bus,
            tokens=tokens,
        )

    await send()
    (files_config.documents_dir / row.path).unlink()
    await send()

    rendered = [
        fact.kind
        for fact in await document_history(session, user_id=user_id, document_id=document_id)
        if fact.kind == "rendered"
    ]
    assert len(rendered) == 2, "свежий файл не пересобирается, пропавший — пересобирается"
    row = await DocumentFileRepository(session).get(document_id, DOCX)
    assert row is not None and storage.exists(row.path)


async def test_send_publishes_only_committed_ready_documents(
    session: AsyncSession, redis, files_config: FilesConfig
) -> None:
    """Бот качает файл другим соединением сразу по событию: к публикации запись
    о файле уже в базе. Документ, вернувшийся в черновик, не уходит даже со
    «свежим» файлом."""
    from core.db.repositories import DownloadTokenRepository
    from core.events import EventBus
    from core.usecases.documents import send_document_to_chat

    user_id = await make_user(session, max_user_id=77)
    document_id = await _ready_document(session, user_id)
    bus = EventBus(redis, stream_to_bot="test:to_bot", source="test", maxlen=100)
    publish = bus.document_ready
    open_transaction_at_publish: list[bool] = []

    async def spy(event):  # type: ignore[no-untyped-def]
        open_transaction_at_publish.append(session.in_transaction())
        return await publish(event)

    bus.document_ready = spy  # type: ignore[method-assign]

    async def send() -> None:
        await send_document_to_chat(
            session,
            user_id=user_id,
            max_user_id=77,
            document_id=document_id,
            fmt=DOCX,
            cfg=files_config,
            bus=bus,
            tokens=DownloadTokenRepository(redis),
        )

    await send()
    assert open_transaction_at_publish == [False], "событие — только после коммита"

    await set_fields(
        session,
        user_id=user_id,
        document_id=document_id,
        values={"total": FieldValue("450 000", ValueSource.AGENT, confirmed=False)},
    )
    with pytest.raises(ConflictError):
        await send()


def test_file_name_is_safe_for_the_bot() -> None:
    from core.usecases.documents.files import build_filename

    assert build_filename("Счёт/для Альфы", "pdf") == "Счёт для Альфы.pdf"
    assert build_filename("Строка\nвторая\tтаб", "docx") == "Строка вторая таб.docx"
    assert build_filename("....", "docx") == "document.docx"
    assert len(build_filename("Я" * 300, "docx").encode()) <= 160
