"""Сумма прописью, дата словами и варианты записи значения в шаблоне."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.domain.documents import (
    FieldSpec,
    FieldType,
    FieldValue,
    account_key_valid,
    fill_context,
    fill_text_template,
    parse_date,
    template_markers,
    validate_fields,
)
from core.domain.words import date_long, money_words, number_words


@pytest.mark.parametrize(
    ("number", "words"),
    [
        (0, "ноль"),
        (1, "один"),
        (12, "двенадцать"),
        (21, "двадцать один"),
        (1000, "одна тысяча"),
        (2000, "две тысячи"),
        (5000, "пять тысяч"),
        (11000, "одиннадцать тысяч"),
        (21000, "двадцать одна тысяча"),
        (120000, "сто двадцать тысяч"),
        (2_500_000, "два миллиона пятьсот тысяч"),
        (1_000_000_001, "один миллиард один"),
    ],
)
def test_number_words(number: int, words: str) -> None:
    assert number_words(number) == words


def test_money_and_date_words() -> None:
    assert money_words(Decimal("10000")) == "Десять тысяч рублей 00 копеек"
    assert money_words(Decimal("1.01")) == "Один рубль 01 копейка"
    assert money_words(Decimal("22.03")) == "Двадцать два рубля 03 копейки"
    assert date_long(date(2026, 9, 1)) == "«01» сентября 2026 г."


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [
        ("«28» сентября 2026 г.", date(2026, 9, 28)),
        ('"01" января 2016 г.', date(2016, 1, 1)),
        ("1 мая 2026", date(2026, 5, 1)),
        ("31 февраля 2026", None),
        ("5 брюмера 2026", None),
    ],
)
def test_dates_written_in_words_are_parsed(raw: str, parsed: date | None) -> None:
    assert parse_date(raw) == parsed


def test_template_variants_of_one_value() -> None:
    specs = (
        FieldSpec("total", "Сумма", FieldType.MONEY),
        FieldSpec("quantity", "Количество", FieldType.INTEGER),
        FieldSpec("date", "Дата", FieldType.DATE),
    )
    context = fill_context(
        specs,
        {
            "total": FieldValue("120000.50"),
            "quantity": FieldValue("4"),
            "date": FieldValue("2026-09-28"),
        },
    )
    body = (
        "{{total|rub}} ({{ total | rub_words }}) рублей {{total|kop}} копеек; "
        "цена {{total|per:quantity}}; {{date|long}}; «{{date|day}}» {{date|month}} 20{{date|yy}}"
    )
    assert fill_text_template(body, context) == (
        "120 000 (сто двадцать тысяч) рублей 50 копеек; цена 30 000,13; "
        "«28» сентября 2026 г.; «28» сентября 2026"
    )
    assert fill_text_template("{{total|words}}", {}) == "__________", "пустое — прочерк"
    assert template_markers(body) == ["total", "date"], "вариант — не отдельное поле"


def test_correspondent_account_is_keyed_by_the_bank() -> None:
    assert account_key_valid("30101810400000000225", "044525225", correspondent=True)
    assert not account_key_valid("30101810400000000226", "044525225", correspondent=True)
    specs = (
        FieldSpec("seller_bic", "БИК", FieldType.BIC),
        FieldSpec("seller_account", "Р/с", FieldType.ACCOUNT),
        FieldSpec("seller_corr_account", "К/с", FieldType.ACCOUNT),
    )
    good = validate_fields(
        specs,
        {
            "seller_bic": FieldValue("044525225"),
            "seller_account": FieldValue("40702810438000123459"),
            "seller_corr_account": FieldValue("30101810400000000225"),
        },
    )
    assert good.errors == ()
    bad = validate_fields(
        specs,
        {"seller_bic": FieldValue("044525225"), "seller_corr_account": FieldValue("3" * 20)},
    )
    assert [error.key for error in bad.errors] == ["seller_corr_account"]
