"""Файл-образец шаблона: текст из DOCX и PDF, сборка документа в оформлении DOCX."""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document
from docx.oxml import parse_xml

from core.domain.places import Place, apply_places, label_of, place_spans
from core.files import (
    TemplateFileError,
    docx_layout,
    docx_lines,
    fill_docx,
    mark_blank_cells,
    pdf_lines,
)
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


def _blank_form() -> bytes:
    """Бланк, где места — пустые ячейки с линейкой: «ИНН [____]», подстрочник под ней."""
    document = Document()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "ИНН"
    table.cell(1, 1).text = "цифрами"
    border = (
        '<w:tcBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:bottom w:val="single" w:sz="4" w:color="000000"/></w:tcBorders>'
    )
    table.cell(0, 1)._tc.get_or_add_tcPr().append(parse_xml(border))
    document.add_paragraph("Итого: {{total|words}}")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_blank_cells_get_label_marks_and_stay_empty_without_value() -> None:
    marked = mark_blank_cells(_blank_form())
    assert marked is not None
    assert "{{ИНН (цифрами)}}" in docx_lines(marked)
    assert docx_layout(marked)[0] == "ИНН  {{ИНН (цифрами)}}", "строка таблицы — одна строка"
    assert mark_blank_cells(offer_docx()) is None, "линеек-ячеек нет — файл не трогаем"

    places = [("inn", Place("{{ИНН (цифрами)}}"))]
    empty = fill_docx(marked, places=places, context={}, blank="__________")
    assert docx_lines(empty)[:2] == ["ИНН", ""], "пустое значение — пустая ячейка, как в бланке"
    assert "Итого: __________" in docx_lines(empty), "в тексте пустое — прочерк"

    filled = fill_docx(
        marked,
        places=places,
        context={"inn": "7707083893", "total|words": "Сто рублей 00 копеек"},
        blank="__________",
    )
    assert docx_lines(filled)[1] == "7707083893"
    assert "Итого: Сто рублей 00 копеек" in docx_lines(filled), "вариант записи из маркера"
