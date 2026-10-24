"""Свой шаблон из файла-образца: места находят метки или помощник, человек
проверяет, документ собирается в оформлении файла."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
from docx import Document as DocxDocument
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldType, FieldValue, format_money
from core.domain.exceptions import AppError, NotFoundError, ValidationError
from core.domain.places import Place
from core.files import FilesConfig, docx_lines
from core.llm import LLMUnavailableError
from core.usecases.agent import import_template_file
from core.usecases.agent.template_import import chunks, suggest_places
from core.usecases.documents import (
    DOCX,
    TemplateField,
    TemplateInput,
    create_draft,
    create_organization,
    create_template,
    get_document,
    get_template,
    load_document_file,
    render_document,
    set_fields,
    update_template,
)
from tests.fakes import FakeLLM
from tests.samples import offer_docx, text_pdf
from tests.usecases.test_documents import make_user

LIMIT = 10 * 1024 * 1024
ASSISTANT_REPLY = {
    "title": "Коммерческое предложение",
    # Помощник видит весь текст: его вид важнее слов в названии файла.
    "kind": "contract",
    "places": [
        {
            "text": "ООО «Альфа»",
            "before": "",
            "label": "Название клиента",
            "type": "text",
            "key": "client_name",
        },
        {
            "text": "ООО «Мастер»",
            "before": "",
            "label": "Моя организация",
            "type": "text",
            "key": "seller_name",
        },
        {"text": "7707083893", "before": "", "label": "ИНН", "type": "text", "key": "seller_inn"},
        {"text": "180 000", "before": "", "label": "Стоимость", "type": "money", "key": "total"},
        {
            "text": "монтаж оборудования",
            "before": "",
            "label": "Работы",
            "type": "multiline",
            "key": "",
        },
        {
            "text": "________",
            "before": "Заказчик: ",
            "label": "Подписант клиента",
            "type": "name",
            "key": "client_director",
        },
        # Линия без подписи совпала бы со всеми линиями бланка.
        {"text": "________", "before": "", "label": "Подпись", "type": "text", "key": ""},
        # Модель переписала кавычки — место всё равно находится, как в файле.
        {
            "text": 'ООО "Альфа"',
            "before": "",
            "label": "Название клиента",
            "type": "text",
            "key": "client_name",
        },
        # Выдуманного фрагмента в файле нет — место отбрасывается.
        {
            "text": "ООО «Гамма»",
            "before": "",
            "label": "Название клиента",
            "type": "text",
            "key": "client_name",
        },
        {
            "text": "14",
            "before": "",
            "label": "Срок оплаты",
            "type": "integer",
            "key": "secret_key",
        },
    ],
}


async def test_assistant_finds_places_and_server_keeps_only_real_ones(
    session: AsyncSession,
) -> None:
    user_id = await make_user(session)
    llm = FakeLLM(json_reply=ASSISTANT_REPLY)

    draft = await import_template_file(
        session,
        user_id=user_id,
        data=offer_docx(),
        filename="Фирменный_КП.docx",
        llm=llm,
        max_bytes=LIMIT,
    )

    assert (draft.format, draft.found_by, draft.title) == (
        "docx",
        "assistant",
        "Коммерческое предложение",
    )
    assert draft.file_id is not None
    by_label = {field.label: field for field in draft.fields}
    assert by_label["Название клиента"].places == (Place("ООО «Альфа»"),)
    assert by_label["ИНН"].type is FieldType.INN, "тип реквизита — по ключу"
    assert by_label["Подписант клиента"].places == (Place("________", "Заказчик: "),)
    assert by_label["Подписант клиента"].required is False
    assert by_label["Срок оплаты"].key == "", "ключ не из каталога — своё поле"
    assert "Подпись" not in by_label
    (_, messages, _) = llm.calls[0]
    assert "ООО «Альфа»" in messages[1].content
    assert draft.kind == "contract"


async def test_marks_in_the_file_are_used_without_the_assistant(session: AsyncSession) -> None:
    user_id = await make_user(session)
    llm = FakeLLM(json_reply=ASSISTANT_REPLY)

    draft = await import_template_file(
        session,
        user_id=user_id,
        data=offer_docx(marked=True),
        filename="КП.docx",
        llm=llm,
        max_bytes=LIMIT,
    )

    assert draft.found_by == "markers" and llm.calls == []
    assert draft.kind == "offer", "без помощника вид — по названию файла и заголовку"
    assert [(f.label, f.places) for f in draft.fields] == [
        ("Название клиента", (Place("{{ Название клиента }}"),)),
        ("Сумма", (Place("{{Сумма}}"),)),
    ]
    assert draft.title == "КП"


async def test_assistant_outage_leaves_places_to_the_person(session: AsyncSession) -> None:
    user_id = await make_user(session)
    down = await import_template_file(
        session,
        user_id=user_id,
        data=offer_docx(),
        filename="a.docx",
        llm=FakeLLM(error=LLMUnavailableError("нет сети")),
        max_bytes=LIMIT,
    )
    off = await import_template_file(
        session, user_id=user_id, data=offer_docx(), filename="a.docx", llm=None, max_bytes=LIMIT
    )
    # Без помощника места ищут правила: подпись с двоеточием, линейки, реквизиты.
    assert down.found_by == off.found_by == "rules"
    by_label = {field.label: field for field in off.fields}
    assert by_label["Для"].places == (Place("ООО «Альфа»", "Для: "),)
    assert by_label["ИНН"].type is FieldType.INN
    assert by_label["Заказчик"].places == (Place("________", "Заказчик: "),)
    assert not any(field.required for field in off.fields), "правила только подсказывают"
    assert down.notice and "не ответил" in down.notice
    assert off.notice and "выключен" in off.notice and "проверьте" in off.notice


async def test_nothing_found_leaves_places_to_the_person(session: AsyncSession) -> None:
    user_id = await make_user(session)
    document = DocxDocument()
    document.add_paragraph("Просто текст без данных")
    buffer = BytesIO()
    document.save(buffer)
    draft = await import_template_file(
        session,
        user_id=user_id,
        data=buffer.getvalue(),
        filename="a.docx",
        llm=None,
        max_bytes=LIMIT,
    )
    assert (draft.found_by, draft.fields) == ("none", ())
    assert draft.notice and "сами" in draft.notice


async def test_pdf_is_kept_as_a_sample_and_scans_are_refused(session: AsyncSession) -> None:
    user_id = await make_user(session)
    draft = await import_template_file(
        session,
        user_id=user_id,
        data=text_pdf(["Offer for ACME Corp", "Total: 100 USD"]),
        filename="offer.pdf",
        llm=None,
        max_bytes=LIMIT,
    )
    # PDF хранится образцом, как DOCX: документ соберётся на его листе.
    assert (draft.format, draft.kind) == ("pdf", "other") and draft.file_id is not None
    assert draft.text.startswith("Offer for ACME Corp")

    with pytest.raises(AppError) as scan:
        await import_template_file(
            session,
            user_id=user_id,
            data=text_pdf([]),
            filename="scan.pdf",
            llm=None,
            max_bytes=LIMIT,
        )
    assert scan.value.code == "template.file_unreadable"
    with pytest.raises(AppError) as other:
        await import_template_file(
            session, user_id=user_id, data=b"GIF89a", filename="x.gif", llm=None, max_bytes=LIMIT
        )
    assert other.value.status_code == 415


def _fields(**places: Place) -> tuple[TemplateField, ...]:
    labels = {
        "client_name": "Название клиента",
        "seller_name": "Название продавца",
        "total": "Сумма",
        "works": "Работы",
    }
    types = {"total": FieldType.MONEY, "works": FieldType.MULTILINE}
    return tuple(
        TemplateField(key, labels[key], types.get(key, FieldType.TEXT), places=(place,))
        for key, place in places.items()
    )


async def test_document_is_built_inside_the_sample(
    session: AsyncSession, files_config: FilesConfig
) -> None:
    user_id = await make_user(session)
    await create_organization(
        session, user_id=user_id, name="ИП Иванов", values={"inn": "500100732259"}
    )
    draft = await import_template_file(
        session, user_id=user_id, data=offer_docx(), filename="КП.docx", llm=None, max_bytes=LIMIT
    )
    fields = _fields(
        client_name=Place("ООО «Альфа»"),
        seller_name=Place("ООО «Мастер»"),
        total=Place("180 000"),
        works=Place("монтаж оборудования"),
    )

    template = await create_template(
        session,
        user_id=user_id,
        data=TemplateInput("Фирменное КП", "", "", fields, file_id=draft.file_id),
    )

    assert template.body_format == "docx" and template.file is not None
    assert "Для: {{client_name}}" in template.body
    assert "Типовые условия: оплата в течение 14 дней." in template.preview
    full = await get_template(session, user_id=user_id, template_id=template.id)
    assert full.file is not None and full.file.text == draft.text

    document = await create_draft(session, user_id=user_id, template_id=template.id)
    assert document.values["seller_name"].value == "ИП Иванов"
    filled = await set_fields(
        session,
        user_id=user_id,
        document_id=document.id,
        values={
            "client_name": FieldValue("ООО «Бета»"),
            "total": FieldValue("250000"),
            "works": FieldValue("Монтаж и наладка"),
        },
    )
    assert filled.ready
    await render_document(
        session, user_id=user_id, document_id=document.id, fmt=DOCX, cfg=files_config
    )
    _, data = await load_document_file(
        session, user_id=user_id, document_id=document.id, fmt=DOCX, cfg=files_config
    )
    lines = docx_lines(data)
    assert lines[0] == "ИП Иванов · ИНН 7707083893", "шапка образца — с реквизитами из профиля"
    assert "Для: ООО «Бета»" in lines and f"{format_money(Decimal(250000))} руб." in lines
    client = DocxDocument(BytesIO(data)).paragraphs[1]
    assert any(run.text == "ООО «Бета»" and run.bold for run in client.runs)


async def test_places_are_checked_against_the_sample(session: AsyncSession) -> None:
    owner = await make_user(session, max_user_id=1)
    stranger = await make_user(session, max_user_id=2)
    draft = await import_template_file(
        session, user_id=owner, data=offer_docx(), filename="КП.docx", llm=None, max_bytes=LIMIT
    )

    with pytest.raises(ValidationError) as missing:
        await create_template(
            session,
            user_id=owner,
            data=TemplateInput(
                "КП", "", "", _fields(client_name=Place("ООО «Гамма»")), file_id=draft.file_id
            ),
        )
    assert "в файле нет текста «ООО «Гамма»»" in missing.value.public_message
    with pytest.raises(NotFoundError):
        await create_template(
            session,
            user_id=stranger,
            data=TemplateInput(
                "КП", "", "", _fields(client_name=Place("ООО «Альфа»")), file_id=draft.file_id
            ),
        )


async def test_editing_places_keeps_old_documents_on_the_same_sample(
    session: AsyncSession,
) -> None:
    user_id = await make_user(session)
    draft = await import_template_file(
        session, user_id=user_id, data=offer_docx(), filename="КП.docx", llm=None, max_bytes=LIMIT
    )
    data = TemplateInput(
        "КП", "", "", _fields(client_name=Place("ООО «Альфа»")), file_id=draft.file_id
    )
    template = await create_template(session, user_id=user_id, data=data)
    old = await create_draft(session, user_id=user_id, template_id=template.id)

    edited = await update_template(
        session,
        user_id=user_id,
        template_id=template.id,
        data=TemplateInput(
            "КП",
            "",
            "",
            _fields(client_name=Place("ООО «Альфа»"), total=Place("180 000")),
            file_id=draft.file_id,
        ),
    )

    assert [field.key for field in edited.fields] == ["client_name", "total"]
    kept = await get_document(session, user_id=user_id, document_id=old.id)
    assert kept.template.id != template.id and kept.template.file == edited.file
    assert [field.key for field in kept.template.fields] == ["client_name"]


def test_long_sample_is_split_by_lines() -> None:
    lines = ["а" * 40, "б" * 40, "в" * 40]
    assert chunks(lines, limit=90) == ["а" * 40 + "\n" + "б" * 40, "в" * 40]
    assert chunks(["", "  "], limit=90) == []


async def test_long_sample_is_read_in_parts() -> None:
    """Реквизиты в конце длинного договора не теряются: вторая часть идёт отдельно."""
    lines = ["Заказчик: ООО «Альфа»", *("Типовое условие." for _ in range(1000)), "ИНН 7707083893"]
    llm = FakeLLM(
        json_replies=[
            {
                "title": "Договор",
                "kind": "contract",
                "places": [
                    {
                        "text": "ООО «Альфа»",
                        "before": "",
                        "label": "Клиент",
                        "type": "text",
                        "key": "",
                    }
                ],
            },
            {
                "title": "",
                "kind": "",
                "places": [
                    {"text": "7707083893", "before": "", "label": "ИНН", "type": "inn", "key": ""}
                ],
            },
        ]
    )
    found = await suggest_places(llm, lines)
    assert [item["text"] for item in found.places] == ["ООО «Альфа»", "7707083893"]
    assert (found.title, found.parts, found.truncated) == ("Договор", 2, False)
    assert "ИНН 7707083893" in llm.calls[1][1][1].content


async def test_fragment_missed_by_the_assistant_is_asked_again() -> None:
    lines = ["Для: ООО «Альфа», срок — 10 дней"]
    missed = {"text": "ООО Альфа", "before": "", "label": "Клиент", "type": "text", "key": ""}
    fixed = {**missed, "text": "ООО «Альфа»"}
    llm = FakeLLM(
        json_replies=[
            {"title": "", "kind": "", "places": [missed]},
            {"title": "", "kind": "", "places": [fixed, {**missed, "text": "Выдумка"}]},
        ]
    )
    found = await suggest_places(llm, lines)
    assert found.places == [fixed], "из второго прохода — только то, что есть в файле"
    assert (found.proposed, found.repaired) == (1, 1)
    (_, repair, _) = llm.calls[1]
    assert "ООО Альфа" in repair[1].content
