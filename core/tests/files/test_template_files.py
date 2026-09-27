"""Файл-образец шаблона: текст из DOCX и PDF, сборка документа в оформлении DOCX."""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document

from core.domain.places import Place, apply_places, label_of, place_spans
from core.files import TemplateFileError, docx_lines, fill_docx, pdf_lines
from tests.samples import offer_docx, text_pdf


def test_place_spans_prefer_longer_places_and_keep_context() -> None:
    line = "Заказчик: ООО «Альфа Плюс», исполнитель: ________, подпись: ________"
    places = [
        ("client_short", Place("Альфа")),
        ("client_name", Place("ООО «Альфа Плюс»")),
        ("seller_director", Place("________", before="исполнитель: ")),
    ]
    assert apply_places(line, places) == (
        "Заказчик: {{client_name}}, исполнитель: {{seller_director}}, подпись: ________"
    )
    assert place_spans("нет совпадений", places) == []
    assert label_of("{{  Название   клиента }}") == "Название клиента"


def test_docx_lines_read_header_body_and_tables() -> None:
    assert docx_lines(offer_docx()) == [
        "ООО «Мастер» · ИНН 7707083893",
        "Коммерческое предложение",
        "Для: ООО «Альфа»",
        "Работы: монтаж оборудования",
        "Стоимость",
        "180 000 руб.",
        "Заказчик: ________\tИсполнитель: ________",
        "Типовые условия: оплата в течение 14 дней.",
    ]


def test_fill_docx_keeps_formatting_of_the_sample() -> None:
    places = [
        ("seller_name", Place("ООО «Мастер»")),
        ("client_name", Place("ООО «Альфа»")),
        ("total", Place("180 000")),
        ("client_director", Place("________", before="Заказчик: ")),
        ("works", Place("монтаж оборудования")),
    ]
    filled = fill_docx(
        offer_docx(),
        places=places,
        context={
            "seller_name": "ИП Иванов",
            "client_name": "ООО «Бета»",
            "total": "250 000,00",
            "works": "Монтаж\nПусконаладка",
        },
        blank="__________",
    )

    assert docx_lines(filled) == [
        "ИП Иванов · ИНН 7707083893",
        "Коммерческое предложение",
        "Для: ООО «Бета»",
        "Работы: Монтаж\nПусконаладка",
        "Стоимость",
        "250 000,00 руб.",
        "Заказчик: __________\tИсполнитель: ________",
        "Типовые условия: оплата в течение 14 дней.",
    ]
    client = Document(BytesIO(filled)).paragraphs[1]
    assert [(run.text, run.bold) for run in client.runs if run.text] == [
        ("Для: ", None),
        ("ООО «Бета»", True),
    ], "значение берёт оформление фрагмента, который заменило"


def test_fill_docx_replaces_marks_written_in_the_file() -> None:
    places = [("client_name", Place("{{ Название клиента }}")), ("total", Place("{{Сумма}}"))]
    filled = fill_docx(
        offer_docx(marked=True), places=places, context={"total": "5,00"}, blank="____"
    )
    lines = docx_lines(filled)
    assert "Для: ____" in lines and "5,00 руб." in lines


def test_unreadable_samples_are_rejected() -> None:
    with pytest.raises(TemplateFileError):
        docx_lines(b"PK\x03\x04 not really a docx")
    with pytest.raises(TemplateFileError):
        pdf_lines(text_pdf([]))
    assert pdf_lines(text_pdf(["Invoice for ACME Corp", "Total: 100 USD"]))[:2] == [
        "Invoice for ACME Corp",
        "Total: 100 USD",
    ]
