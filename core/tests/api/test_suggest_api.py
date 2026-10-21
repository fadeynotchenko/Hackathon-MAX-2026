"""HTTP-контракт подсказок: только под Bearer, вид подсказки из пути, 503 без ключа."""

from __future__ import annotations

from dataclasses import replace

from httpx import AsyncClient

from core.suggest import CompanyRecord
from tests.api.test_documents_api import _auth
from tests.fakes import FakeSuggest

ROMASHKA = CompanyRecord(
    name="ООО «Ромашка»",
    inn="7707083893",
    kpp="773601001",
    ogrn="1027700132195",
    address="г Москва",
    director="Иванов Иван Иванович",
    status="",
    individual=False,
)


async def test_suggest_companies(app, client: AsyncClient, make_init_data) -> None:
    fake = FakeSuggest(companies=[ROMASHKA])
    app.state.api = replace(app.state.api, suggest=fake)
    url = "/api/v1/suggest/company"

    assert (await client.get(url, params={"query": "7707"})).status_code == 401

    headers = await _auth(client, make_init_data)
    response = await client.get(url, params={"query": "7707"}, headers=headers)
    assert response.status_code == 200, response.text
    (item,) = response.json()
    assert item["title"] == "ООО «Ромашка»"
    assert item["values"]["inn"] == "7707083893"

    unknown = await client.get("/api/v1/suggest/fio", params={"query": "ив"}, headers=headers)
    assert unknown.status_code == 422


async def test_suggest_without_key_is_503(client: AsyncClient, make_init_data) -> None:
    headers = await _auth(client, make_init_data)
    response = await client.get("/api/v1/suggest/bank", params={"query": "сбер"}, headers=headers)
    assert response.status_code == 503
    assert response.json()["code"] == "suggest.unavailable"
