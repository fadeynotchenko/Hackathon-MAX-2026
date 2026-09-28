"""Документ по присланному файлу и свой шаблон на основе стандартного бланка."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldValue, ValueSource
from core.domain.exceptions import AppError, ValidationError
from core.files import FilesConfig, docx_lines
from core.usecases.agent import document_from_file
from core.usecases.documents import (
    DOCX,
    TemplateField,
    TemplateInput,
    create_template,
    ensure_builtin_templates,
    get_template,
    keep_template,
    list_templates,
    load_document_file,
    render_document,
    set_fields,
)
from tests.fakes import FakeLLM
from tests.samples import OFFER_PLACES as PLACES
from tests.samples import offer_docx, text_pdf
from tests.usecases.test_documents import make_user

LIMIT = 10 * 1024 * 1024


async def test_document_takes_values_from_the_file(session: AsyncSession, tmp_path: Path) -> None:
    user_id = await make_user(session)
    imported = await document_from_file(
        session,
        user_id=user_id,
        data=offer_docx(),
        filename="КП Альфе.docx",
        llm=FakeLLM(json_reply=PLACES),
        max_bytes=LIMIT,
    )

    document = imported.document
    assert (imported.format, imported.found_by, imported.notice) == ("docx", "assistant", None)
    assert document.values["client_name"] == FieldValue("ООО «Альфа»", ValueSource.FILE)
    assert document.values["total"].value == "180000.00"
    assert document.ready, "в файле уже всё есть — документ готов к сборке"
    labels = {field.key: field.label for field in document.template.fields}
    assert labels == {"client_name": "Название клиента", "total": "Сумма"}
    assert not document.template.in_library, "шаблон под один документ в каталог не попадает"
    assert all(t.id != document.template.id for t in await list_templates(session, user_id=user_id))

    changed = await set_fields(
        session,
        user_id=user_id,
        document_id=document.id,
        values={"client_name": FieldValue("ООО «Бета»"), "total": FieldValue("250 000")},
    )
    cfg = FilesConfig(tmp_path, "soffice", 5)
    await render_document(session, user_id=user_id, document_id=changed.id, fmt=DOCX, cfg=cfg)
    _, data = await load_document_file(
        session, user_id=user_id, document_id=changed.id, fmt=DOCX, cfg=cfg
    )
    text = docx_lines(data)
    assert "Для: ООО «Бета»" in text and "250 000,00 руб." in text
    assert "Работы: монтаж оборудования" in text, "остальное — как в присланном файле"


async def test_invalid_value_from_file_is_shown_not_kept(session: AsyncSession) -> None:
    user_id = await make_user(session)
    places = {
        "title": "Счёт",
        "kind": "invoice",
        "places": [
            {"text": "7707083894", "before": "", "label": "ИНН", "type": "inn", "key": "client_inn"}
        ],
    }
    imported = await document_from_file(
        session,
        user_id=user_id,
        data=text_pdf(["Invoice", "INN 7707083894"]),
        filename="bill.pdf",
        llm=FakeLLM(json_reply=places),
        max_bytes=LIMIT,
    )
    document = imported.document
    assert imported.format == "pdf" and imported.notice and "DOCX" in imported.notice
    assert "client_inn" not in document.values
    assert [error.code for error in document.errors] == ["field.inn_invalid"]
    assert document.template.file is None and "{{client_inn}}" in document.template.body


async def test_file_without_places_is_refused(session: AsyncSession) -> None:
    user_id = await make_user(session)
    with pytest.raises(AppError) as exc:
        await document_from_file(
            session,
            user_id=user_id,
            data=text_pdf(["Just some words"]),
            filename="a.pdf",
            llm=None,
            max_bytes=LIMIT,
        )
    assert exc.value.code == "document.import_empty" and exc.value.status_code == 422


async def test_document_template_can_be_kept_in_the_library(session: AsyncSession) -> None:
    user_id = await make_user(session)
    imported = await document_from_file(
        session,
        user_id=user_id,
        data=offer_docx(),
        filename="КП.docx",
        llm=FakeLLM(json_reply=PLACES),
        max_bytes=LIMIT,
    )
    kept = await keep_template(session, user_id=user_id, template_id=imported.document.template.id)
    assert kept.in_library and kept.file is not None
    assert any(t.id == kept.id for t in await list_templates(session, user_id=user_id))


async def test_own_template_from_the_standard_blank(session: AsyncSession) -> None:
    """«Сделать свой на основе этого» у стандартного бланка: файл тот же, метки
    уже стоят в нём — местам не нужно ничего указывать."""
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    (offer,) = await list_templates(session, user_id=user_id, slug="offer")
    builtin = await get_template(session, user_id=user_id, template_id=offer.id)
    assert builtin.file is not None and builtin.file.text and "{{client_name}}" in builtin.file.text

    fields = tuple(
        TemplateField(
            key=spec.key,
            label="Кому" if spec.key == "client_name" else spec.label,
            type=spec.type,
            required=spec.required,
            default=spec.default,
        )
        for spec in builtin.fields
    )
    own = await create_template(
        session,
        user_id=user_id,
        data=TemplateInput(
            title="Моё КП", description="", body="", fields=fields, file_id=builtin.file.id
        ),
    )
    assert own.file is not None and own.file.id == builtin.file.id
    assert next(f for f in own.fields if f.key == "client_name").label == "Кому"
    assert next(f for f in own.fields if f.key == "vat").default == "не облагается"
    assert "Итого:" in own.preview

    without_client = tuple(field for field in fields if field.key != "client_name")
    with pytest.raises(ValidationError) as exc:
        await create_template(
            session,
            user_id=user_id,
            data=TemplateInput(
                title="Без клиента",
                description="",
                body="",
                fields=without_client,
                file_id=builtin.file.id,
            ),
        )
    assert "{{client_name}}" in str(exc.value), "метку бланка нельзя оставить без поля"
