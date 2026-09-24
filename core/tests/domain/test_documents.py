"""Проверка полей документа: нормализация и контрольные суммы реквизитов."""

from __future__ import annotations

import pytest

from core.domain.documents import (
    FieldSpec,
    FieldType,
    FieldValue,
    ValueSource,
    account_key_valid,
    format_money,
    normalize,
    parse_date,
    parse_money,
    render_context,
    validate_fields,
)

SPECS = (
    FieldSpec("company", "Название", FieldType.TEXT),
    FieldSpec("inn", "ИНН", FieldType.INN),
    FieldSpec("kpp", "КПП", FieldType.KPP, required=False),
    FieldSpec("ogrn", "ОГРН", FieldType.OGRN, required=False),
    FieldSpec("bic", "БИК", FieldType.BIC, required=False),
    FieldSpec("account", "Расчётный счёт", FieldType.ACCOUNT, required=False),
    FieldSpec("total", "Сумма", FieldType.MONEY),
    FieldSpec("due_date", "Оплатить до", FieldType.DATE),
    FieldSpec("email", "Почта", FieldType.EMAIL, required=False),
    FieldSpec("phone", "Телефон", FieldType.PHONE, required=False),
)
BY_KEY = {spec.key: spec for spec in SPECS}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("120 000,50", "120000.50"),
        ("120000.5", "120000.50"),
        ("1 200 ₽", "1200.00"),
        ("150 000 рублей", "150000.00"),
        ("150 000 руб", "150000.00"),
        ("150 тыс. руб.", "150000.00"),
        ("1,555 тыс", "1555.00"),
        ("200к", "200000.00"),
        ("1,5 млн", "1500000.00"),
    ],
)
def test_money_is_normalized(raw: str, expected: str) -> None:
    assert normalize(BY_KEY["total"], raw) == (expected, None)


@pytest.mark.parametrize(
    "raw", ["сто рублей", "-5", "10.555", "NaN", "nan", "Infinity", "-inf", "sNaN", "1e999999"]
)
def test_money_rejects_garbage(raw: str) -> None:
    value, error = normalize(BY_KEY["total"], raw)
    assert value == ""
    assert error is not None and error.code == "field.money_invalid"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("31.12.2026", "2026-12-31"), ("2026-12-31", "2026-12-31"), ("1.1.2027", "2027-01-01")],
)
def test_date_formats_are_interchangeable(raw: str, expected: str) -> None:
    assert normalize(BY_KEY["due_date"], raw) == (expected, None)


def test_money_zero_has_no_minus() -> None:
    assert normalize(BY_KEY["total"], "-0") == ("0.00", None)


def test_money_has_a_ceiling() -> None:
    assert parse_money("999 999 999 999,99") is not None
    assert parse_money("1 000 000 000 000") is None


def test_date_rejects_impossible_day() -> None:
    assert parse_date("31.02.2026") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("01.10.26", "2026-10-01"), ("31.12.2026 г.", "2026-12-31"), ("31.12.2026г", "2026-12-31")],
)
def test_date_as_people_write_it(raw: str, expected: str) -> None:
    assert normalize(BY_KEY["due_date"], raw) == (expected, None)


@pytest.mark.parametrize("raw", ["1.1.1899", "1.1.2101", "01.01.0026"])
def test_date_outside_sane_years_is_rejected(raw: str) -> None:
    assert parse_date(raw) is None


@pytest.mark.parametrize(("raw", "expected"), [("10", "10"), ("10 дней", "10"), ("007", "7")])
def test_integer_accepts_unit_after_number(raw: str, expected: str) -> None:
    spec = FieldSpec("term_days", "Срок, дней", FieldType.INTEGER)
    assert normalize(spec, raw) == (expected, None)


@pytest.mark.parametrize("raw", ["10.5", "-3", "5 рабочих дней", "десять"])
def test_integer_rejects_non_integers(raw: str) -> None:
    spec = FieldSpec("term_days", "Срок, дней", FieldType.INTEGER)
    _, error = normalize(spec, raw)
    assert error is not None and error.code == "field.integer_invalid"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("773601001", "773601001"), ("7736 01 001", "773601001"), ("7736ab001", "7736AB001")],
)
def test_kpp_allows_latin_letters_in_reason_code(raw: str, expected: str) -> None:
    assert normalize(BY_KEY["kpp"], raw) == (expected, None)


def test_bic_of_russian_bank_starts_with_04() -> None:
    assert normalize(BY_KEY["bic"], "044525225") == ("044525225", None)
    _, error = normalize(BY_KEY["bic"], "123456789")
    assert error is not None and error.code == "field.bic_invalid"


@pytest.mark.parametrize("inn", ["7707083893", "500100732259"])
def test_inn_checksum_accepts_real_numbers(inn: str) -> None:
    assert normalize(BY_KEY["inn"], inn) == (inn, None)


@pytest.mark.parametrize("inn", ["7707083894", "1234567890", "770708389"])
def test_inn_checksum_rejects_typos(inn: str) -> None:
    _, error = normalize(BY_KEY["inn"], inn)
    assert error is not None and error.code == "field.inn_invalid"


def test_ogrn_checksum() -> None:
    assert normalize(BY_KEY["ogrn"], "1027700132195") == ("1027700132195", None)
    _, error = normalize(BY_KEY["ogrn"], "1027700132196")
    assert error is not None and error.code == "field.ogrn_invalid"


def test_phone_is_reduced_to_one_shape() -> None:
    assert normalize(BY_KEY["phone"], "8 (916) 123-45-67")[0] == "+79161234567"
    assert normalize(BY_KEY["phone"], "+7 916 123 45 67")[0] == "+79161234567"


def test_account_key_checked_against_bic() -> None:
    # Счёт Сбербанка в своём же банке: ключ сходится только с его БИК.
    assert account_key_valid("40702810438000123459", "044525225")
    assert not account_key_valid("40702810438000123458", "044525225")


def test_validate_reports_missing_and_unknown() -> None:
    result = validate_fields(
        SPECS,
        {
            "company": FieldValue("ООО «Ромашка»"),
            "inn": FieldValue("7707083893"),
            "surprise": FieldValue("нет такого поля"),
        },
    )
    assert [e.code for e in result.errors] == ["field.unknown"]
    assert set(result.missing) == {"total", "due_date"}
    assert not result.ready


def test_account_and_bic_are_checked_together() -> None:
    result = validate_fields(
        SPECS,
        {
            "company": FieldValue("ООО «Ромашка»"),
            "inn": FieldValue("7707083893"),
            "total": FieldValue("1000"),
            "due_date": FieldValue("31.12.2026"),
            "bic": FieldValue("044525225"),
            "account": FieldValue("40702810438000123458"),
        },
    )
    assert [e.code for e in result.errors] == ["field.account_key_invalid"]


def test_account_is_checked_against_bic_of_its_own_side() -> None:
    # Счёт клиента в Сбербанке сверяется с БИК клиента, а не с банком продавца.
    specs = (
        FieldSpec("seller_bic", "БИК", FieldType.BIC),
        FieldSpec("seller_account", "Счёт", FieldType.ACCOUNT),
        FieldSpec("client_bic", "БИК клиента", FieldType.BIC),
        FieldSpec("client_account", "Счёт клиента", FieldType.ACCOUNT),
    )
    result = validate_fields(
        specs,
        {
            "seller_bic": FieldValue("044030653"),
            "client_bic": FieldValue("044525225"),
            "client_account": FieldValue("40702810438000123459"),
        },
    )
    assert result.errors == ()


def test_recognized_values_wait_for_confirmation() -> None:
    result = validate_fields(
        SPECS,
        {
            "company": FieldValue(
                "ООО «Ромашка»", ValueSource.OCR, confidence=0.82, confirmed=False
            ),
            "inn": FieldValue("7707083893", ValueSource.OCR, confirmed=True),
            "total": FieldValue("1000"),
            "due_date": FieldValue("31.12.2026"),
        },
    )
    assert result.errors == ()
    assert result.missing == ()
    assert result.unconfirmed == ("company",)
    assert not result.ready


def test_ready_when_everything_filled_and_confirmed() -> None:
    result = validate_fields(
        SPECS,
        {
            "company": FieldValue("ООО «Ромашка»"),
            "inn": FieldValue("7707083893"),
            "total": FieldValue("120 000,50"),
            "due_date": FieldValue("31.12.2026"),
        },
    )
    assert result.ready


def test_render_context_is_human_readable() -> None:
    values = validate_fields(
        SPECS,
        {
            "company": FieldValue("ООО «Ромашка»"),
            "inn": FieldValue("7707083893"),
            "total": FieldValue("120000.5"),
            "due_date": FieldValue("2026-12-31"),
        },
    ).values
    context = render_context(SPECS, values)
    assert context["total"] == format_money(parse_money("120000.50"))
    assert context["total"] == "120 000,50"
    assert context["due_date"] == "31.12.2026"
    assert context["kpp"] == ""


def test_phone_is_readable_in_document() -> None:
    values = {"phone": FieldValue("+79161234567")}
    assert render_context(SPECS, values)["phone"] == "+7 916 123-45-67"


@pytest.mark.parametrize("raw", ["ООО\x00", "Ромашка\x07", "a\x1bb"])
def test_control_characters_are_refused_not_crashing(raw: str) -> None:
    _, error = normalize(BY_KEY["company"], raw)
    assert error is not None and error.code == "field.control_chars"


def test_invisible_characters_do_not_fill_a_field() -> None:
    assert normalize(BY_KEY["company"], "​﻿") == ("", None)
    assert normalize(BY_KEY["company"], "ООО​ «Ромашка»") == ("ООО «Ромашка»", None)


def test_only_ascii_digits_make_requisites() -> None:
    _, error = normalize(BY_KEY["inn"], "٧٧٠٧٠٨٣٨٩٣")
    assert error is not None and error.code == "field.inn_invalid"


def test_text_and_integer_have_sane_limits() -> None:
    _, error = normalize(BY_KEY["company"], "я" * 100_000)
    assert error is not None and error.code == "field.too_long"
    spec = FieldSpec("term_days", "Срок, дней", FieldType.INTEGER)
    _, error = normalize(spec, "9" * 5000)
    assert error is not None and error.code == "field.too_long"
    _, error = normalize(spec, "9" * 20)
    assert error is not None and error.code == "field.integer_invalid"
