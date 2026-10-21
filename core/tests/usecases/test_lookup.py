"""Подсказки реквизитов: значения под ключи карточки, короткий запрос, выключенный реестр."""

from __future__ import annotations

import pytest

from core.domain.exceptions import AppError
from core.suggest import AddressRecord, BankRecord, CompanyRecord
from core.usecases.documents import SuggestKind, suggest_requisites
from tests.fakes import FakeSuggest

ROMASHKA = CompanyRecord(
    name="ООО «Ромашка»",
    inn="7707083893",
    kpp="773601001",
    ogrn="1027700132195",
    address="117312, г Москва, ул Вавилова, д 19",
    director="Иванов Иван Иванович",
    status="",
    individual=False,
)


async def test_company_values_use_requisite_keys_and_skip_empty() -> None:
    no_kpp = CompanyRecord(
        name="ИП Петров",
        inn="500100732259",
        kpp="",
        ogrn="",
        address="",
        director="Петров Пётр",
        status="ликвидирована",
        individual=True,
    )
    fake = FakeSuggest(companies=[ROMASHKA, no_kpp])

    first, second = await suggest_requisites(
        SuggestKind.COMPANY, "  ромашка   москва ", client=fake
    )

    assert fake.queries == [("company", "ромашка москва")]
    assert first.title == "ООО «Ромашка»"
    assert first.subtitle == "ИНН 7707083893 · 117312, г Москва, ул Вавилова, д 19"
    assert dict(first.values) == {
        "name": "ООО «Ромашка»",
        "inn": "7707083893",
        "kpp": "773601001",
        "ogrn": "1027700132195",
        "address": "117312, г Москва, ул Вавилова, д 19",
        "director": "Иванов Иван Иванович",
    }
    assert second.subtitle == "ИНН 500100732259 · ликвидирована"
    assert set(second.values) == {"name", "inn", "director"}


async def test_bank_and_address() -> None:
    fake = FakeSuggest(
        banks=[BankRecord("ПАО Сбербанк", "044525225", "30101810400000000225", "г Москва")],
        addresses=[
            AddressRecord("г Москва, ул Тверская, д 1", "125009, г Москва, ул Тверская, д 1")
        ],
    )

    (bank,) = await suggest_requisites(SuggestKind.BANK, "0445", client=fake)
    (address,) = await suggest_requisites(SuggestKind.ADDRESS, "тверская", client=fake)

    assert dict(bank.values) == {
        "bank": "ПАО Сбербанк",
        "bic": "044525225",
        "corr_account": "30101810400000000225",
    }
    assert bank.subtitle == "БИК 044525225 · г Москва"
    assert dict(address.values) == {"address": "125009, г Москва, ул Тверская, д 1"}


async def test_short_query_does_not_reach_registry() -> None:
    fake = FakeSuggest(companies=[ROMASHKA])
    assert await suggest_requisites(SuggestKind.COMPANY, " р ", client=fake) == []
    assert fake.queries == []


@pytest.mark.parametrize("client", [None, FakeSuggest(unavailable=True)])
async def test_unavailable_registry_is_503(client: FakeSuggest | None) -> None:
    with pytest.raises(AppError) as caught:
        await suggest_requisites(SuggestKind.COMPANY, "ромашка", client=client)
    assert (caught.value.status_code, caught.value.code) == (503, "suggest.unavailable")
