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
    [("120 000,50", "120000.50"), ("120000.5", "120000.50"), ("1 200 ₽", "1200.00")],
)
def test_money_is_normalized(raw: str, expected: str) -> None:
    assert normalize(BY_KEY["total"], raw) == (expected, None)


@pytest.mark.parametrize("raw", ["сто рублей", "-5", "10.555"])
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


def test_date_rejects_impossible_day() -> None:
    assert parse_date("31.02.2026") is None


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
