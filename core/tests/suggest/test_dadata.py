"""Адаптер DaData на подменённом транспорте: разбор ответа и временные отказы."""

from __future__ import annotations

import json

import httpx
import pytest

from core.suggest import DadataClient, DadataConfig, SuggestUnavailableError

CFG = DadataConfig(
    api_key="test-key",
    api_url="https://suggestions.dadata.ru/suggestions/api/4_1/rs",
    timeout_seconds=5,
)

LEGAL = {
    "value": "ПАО СБЕРБАНК",
    "data": {
        "type": "LEGAL",
        "inn": "7707083893",
        "kpp": "773601001",
        "ogrn": "1027700132195",
        "name": {"short_with_opf": "ПАО СБЕРБАНК", "full": "СБЕРБАНК РОССИИ"},
        "management": {"name": "Греф Герман Оскарович", "post": "ПРЕЗИДЕНТ"},
        "address": {
            "value": "г Москва, ул Вавилова, д 19",
            "unrestricted_value": "117312, г Москва, ул Вавилова, д 19",
        },
        "state": {"status": "ACTIVE"},
    },
}
INDIVIDUAL = {
    "value": "ИП Иванов Иван Иванович",
    "data": {
        "type": "INDIVIDUAL",
        "inn": "500100732259",
        "kpp": None,
        "ogrn": "304500116000157",
        "name": {"short_with_opf": "ИП Иванов Иван Иванович", "full": "Иванов Иван Иванович"},
        "management": None,
        "address": None,
        "state": {"status": "LIQUIDATED"},
    },
}


def _client(handler) -> DadataClient:
    return DadataClient(CFG, transport=httpx.MockTransport(handler))


async def test_companies_map_registry_fields_and_send_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"suggestions": [LEGAL, INDIVIDUAL, "мусор"]})

    client = _client(handler)
    legal, individual = await client.companies("сбер", count=5)
    await client.aclose()

    assert seen[0].url.path.endswith("/suggest/party")
    assert seen[0].headers["Authorization"] == "Token test-key"
    assert json.loads(seen[0].content) == {"query": "сбер", "count": 5}
    assert (legal.name, legal.inn, legal.kpp, legal.director, legal.status) == (
        "ПАО СБЕРБАНК",
        "7707083893",
        "773601001",
        "Греф Герман Оскарович",
        "",
    )
    assert legal.address == "117312, г Москва, ул Вавилова, д 19"
    # У ИП подписант — сам предприниматель, КПП и адреса в подсказке нет.
    assert (individual.director, individual.kpp, individual.address) == (
        "Иванов Иван Иванович",
        "",
        "",
    )
    assert individual.individual and individual.status == "ликвидирована"


async def test_banks_and_addresses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bank"):
            item = {
                "value": "ПАО Сбербанк",
                "data": {
                    "bic": "044525225",
                    "correspondent_account": "30101810400000000225",
                    "address": {"value": "г Москва, ул Вавилова, д 19"},
                },
            }
        else:
            item = {"value": "г Москва, ул Тверская, д 1", "unrestricted_value": "125009, г Москва"}
        return httpx.Response(200, json={"suggestions": [item]})

    client = _client(handler)
    (bank,) = await client.banks("044525225", count=3)
    (address,) = await client.addresses("тверская 1", count=3)
    await client.aclose()

    assert (bank.name, bank.bic, bank.corr_account) == (
        "ПАО Сбербанк",
        "044525225",
        "30101810400000000225",
    )
    assert (address.short, address.full) == ("г Москва, ул Тверская, д 1", "125009, г Москва")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, json={"message": "Forbidden"}),
        httpx.Response(429, json={"message": "Too many"}),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json={"oops": []}),
    ],
)
async def test_refusals_are_unavailable(response: httpx.Response) -> None:
    client = _client(lambda _request: response)
    with pytest.raises(SuggestUnavailableError):
        await client.companies("сбер", count=5)
    await client.aclose()


async def test_network_error_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    client = _client(handler)
    with pytest.raises(SuggestUnavailableError, match="ConnectTimeout"):
        await client.addresses("москва", count=5)
    await client.aclose()
