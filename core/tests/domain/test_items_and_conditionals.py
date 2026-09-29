"""Позиции счёта и условные куски шаблона: разбор, контекст и текстовая подстановка."""

from __future__ import annotations

import json

import pytest

from core.domain.documents import (
    BLANK,
    FieldSpec,
    FieldType,
    FieldValue,
    fill_context,
    fill_text_template,
    legacy_items,
    normalize,
    render_context,
    template_markers,
)

ITEMS = FieldSpec("items", "Позиции", FieldType.ITEMS)
VAT = FieldSpec("vat_rate", "Ставка НДС", FieldType.INTEGER, required=False)
SPECS = (ITEMS, VAT)


def _items(*rows: dict[str, str]) -> str:
    return json.dumps(list(rows), ensure_ascii=False)


def test_items_are_normalized_to_canonical_json() -> None:
    raw = _items(
        {"name": "  Ноутбук   Lenovo ", "qty": "3", "unit": "шт.", "price": "78 500"},
        {"name": "", "quantity": "", "price": ""},
        {"name": "Настройка", "quantity": "4,5", "price": "2 500,50"},
    )
    value, error = normalize(ITEMS, raw)
    assert error is None
    assert json.loads(value) == [
        {"name": "Ноутбук Lenovo", "quantity": "3", "unit": "шт.", "price": "78500.00"},
        {"name": "Настройка", "quantity": "4.5", "unit": "", "price": "2500.50"},
    ], "пустая строка формы пропущена, количество по умолчанию — 1, числа строками"
    assert normalize(ITEMS, _items({"name": "", "price": ""})) == ("", None), "пусто — не заполнено"
    single, _ = normalize(ITEMS, json.dumps({"name": "Сайт", "price": 100}))
    assert json.loads(single)[0]["price"] == "100.00", "одна позиция объектом — тоже список"


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        ("Разработка сайта", "не читается"),
        (_items({"name": "Сайт"}), "укажите цену позиции 1"),
        (_items({"name": "Сайт", "price": "дорого"}), "цена позиции 1 не похожа на сумму"),
        (_items({"name": "Сайт", "price": "1"}, {"price": "5"}), "у позиции 2 нет наименования"),
        (_items({"name": "Сайт", "quantity": "0", "price": "1"}), "количество в позиции 1"),
        (_items({"name": "Сайт", "quantity": "1,0005", "price": "1"}), "количество в позиции 1"),
        (_items(*[{"name": "x", "price": "1"}] * 101), "не больше 100 позиций"),
        (_items({"name": "x", "quantity": "999999", "price": "999999999"}), "больше триллиона"),
    ],
)
def test_bad_items_are_explained_with_the_row_number(raw: str, problem: str) -> None:
    value, error = normalize(ITEMS, raw)
    assert value == "" and error is not None and error.code == "field.items_invalid"
    assert problem in error.message and error.message.startswith("«Позиции»: ")


def test_items_give_rows_totals_and_money_variants() -> None:
    raw = _items(
        {"name": "Ноутбук", "quantity": "3", "unit": "шт.", "price": "78500"},
        {"name": "Доставка", "price": "1500"},
    )
    value, _ = normalize(ITEMS, raw)
    context = fill_context(SPECS, {"items": FieldValue(value), "vat_rate": FieldValue("20")})
    assert context["items|count"] == "2"
    assert context["items|sum"] == "237 000,00"
    assert context["items|words"] == "Двести тридцать семь тысяч рублей 00 копеек"
    assert context["items|vat:vat_rate"] == "39 500,00", "НДС 20% в том числе"
    assert (context["items.1.n"], context["items.1.amount"]) == ("1", "235 500,00")
    assert (context["items.2.quantity"], context["items.2.unit"]) == ("1", "")
    assert render_context(SPECS, {"items": FieldValue(value)})["items"] == (
        "1. Ноутбук — 3 шт. × 78 500,00 = 235 500,00\n2. Доставка — 1 × 1 500,00 = 1 500,00"
    ), "позиции текстом — для чата и помощника"


def test_row_markers_belong_to_the_list_field() -> None:
    body = "{{items.n}}  {{items.name}}  {{items.price}}\nИтого {{items|sum}}, НДС {{items|vat:vat_rate}}"
    assert template_markers(body) == ["items", "vat_rate"]


def test_text_template_repeats_the_row_per_position() -> None:
    value, _ = normalize(
        ITEMS,
        _items(
            {"name": "Сайт", "price": "100"},
            {"name": "Хостинг", "unit": "мес.", "quantity": "2", "price": "5"},
        ),
    )
    context = fill_context(SPECS, {"items": FieldValue(value)})
    body = "№  Наименование  Кол-во  Ед.\n{{items.n}}  {{items.name}}  {{items.quantity}}  {{items.unit}}  {{note}}\nВсего {{items|count}}"
    assert fill_text_template(body, context | {"note": "до 01.10"}).split("\n") == [
        "№  Наименование  Кол-во  Ед.",
        "1  Сайт  1    до 01.10",
        "2  Хостинг  2  мес.  ",
        "Всего 2",
    ], "значение документа в строке позиций — только в первой, как объединённая ячейка"
    empty = fill_text_template(body, {})
    assert empty.split("\n")[1] == "  ".join([BLANK] * 5), (
        "пустой список — строка для записи от руки"
    )


def test_conditional_piece_disappears_with_its_label() -> None:
    body = (
        "Поставщик: {{name}}[[, ИНН {{inn}}]][[, КПП {{kpp}}]]\n"
        "[[Порядок оплаты: {{terms}}.]]\n"
        "[[Тел.: {{phone}}]][[, e-mail: {{email}}]][[, сайт: {{site}}]]\n"
        "Адрес  [[{{address}}]]\n"
        "Номер: {{number}}"
    )
    context = {"name": "ООО «Ромашка»", "inn": "7728417603", "email": "a@b.example"}
    assert fill_text_template(body, context).split("\n") == [
        "Поставщик: ООО «Ромашка», ИНН 7728417603",
        "E-mail: a@b.example",
        f"Номер: {BLANK}",
    ], "строка из одной подписи уходит, запятая в начале — тоже, пустое вне куска — линия"
    full = context | {
        "kpp": "772801001",
        "phone": "+7",
        "site": "x.ru",
        "terms": "50%",
        "address": "Москва",
    }
    lines = fill_text_template(body, full).split("\n")
    assert lines[:4] == [
        "Поставщик: ООО «Ромашка», ИНН 7728417603, КПП 772801001",
        "Порядок оплаты: 50%.",
        "Тел.: +7, e-mail: a@b.example, сайт: x.ru",
        "Адрес  Москва",
    ]
    assert "[[" not in fill_text_template(body, {}) and "]]" not in fill_text_template(body, {})


def test_old_single_item_invoice_becomes_one_position() -> None:
    values = {
        "item": FieldValue("Сопровождение сайта"),
        "quantity": FieldValue("3"),
        "unit": FieldValue("мес."),
        "total": FieldValue("100000.00"),
    }
    converted = legacy_items(values)
    assert converted is not None
    assert json.loads(converted.value) == [
        {"name": "Сопровождение сайта", "quantity": "3", "unit": "мес.", "price": "33333.33"}
    ]
    assert legacy_items({"item": FieldValue("Без суммы")}) is None
    assert legacy_items({"total": FieldValue("1.00")}) is None


def test_section_heading_follows_its_lines_and_else_wording_replaces_a_blank() -> None:
    """[[?…]] держится, пока заполнено хоть одно поле раздела, {{key|hide}} в
    нём не печатается; [[!…]] — формулировка на случай, когда поле пусто."""
    body = (
        "[[?Условия{{pay|hide}}{{term|hide}}]]\n"
        "[[Оплата: {{pay}}]]\n"
        "[[Срок: {{term}}]]\n"
        "Отказ: [[выплата {{fee}} руб.]][[!{{fee|hide}}возмещение расходов.]]"
    )
    assert fill_text_template(body, {}).split("\n") == ["Отказ: возмещение расходов."]
    assert fill_text_template(body, {"term": "5 дней", "fee": "1 000,00"}).split("\n") == [
        "Условия",
        "Срок: 5 дней",
        "Отказ: выплата 1 000,00 руб.",
    ]
