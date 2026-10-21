"""Адаптер подсказок DaData: организации и ИП из ЕГРЮЛ/ЕГРИП, банки по БИК, адреса ФИАС.

Ручки подсказок пускают по одному API-ключу (``Authorization: Token``) — секретный
ключ нужен только стандартизации, её мы не зовём. Ответ разбирается здесь: имена
полей DaData дальше адаптера не уходят.

Подсказки зовутся на каждое слово, которое набирает человек: таймаут короткий,
повторов нет. Не ответил сервис — поле остаётся обычным полем ввода, ждать
подсказку дольше, чем набрать значение руками, незачем.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from core.suggest.client import (
    AddressRecord,
    BankRecord,
    CompanyRecord,
    SuggestUnavailableError,
)
from core.suggest.config import DadataConfig

# Подписи к записи в списке; действующая организация подписи не получает.
_STATUS_LABEL = {
    "LIQUIDATING": "ликвидируется",
    "LIQUIDATED": "ликвидирована",
    "BANKRUPT": "банкротство",
    "REORGANIZING": "реорганизуется",
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    return value if isinstance(value, Mapping) else {}


def _company(item: Mapping[str, Any]) -> CompanyRecord:
    data = _section(item, "data")
    names = _section(data, "name")
    address = _section(data, "address")
    individual = data.get("type") == "INDIVIDUAL"
    # У ИП руководителя в реестре нет: подписывает сам предприниматель, его ФИО — в name.full.
    director = (
        _text(names.get("full")) if individual else _text(_section(data, "management").get("name"))
    )
    status = _text(_section(data, "state").get("status"))
    return CompanyRecord(
        name=_text(names.get("short_with_opf")) or _text(item.get("value")),
        inn=_text(data.get("inn")),
        kpp=_text(data.get("kpp")),
        ogrn=_text(data.get("ogrn")),
        # В документ — адрес с индексом: так его пишут в реквизитах.
        address=_text(address.get("unrestricted_value")) or _text(address.get("value")),
        director=director,
        status=_STATUS_LABEL.get(status, ""),
        individual=individual,
    )


def _bank(item: Mapping[str, Any]) -> BankRecord:
    data = _section(item, "data")
    return BankRecord(
        name=_text(item.get("value")) or _text(_section(data, "name").get("payment")),
        bic=_text(data.get("bic")),
        corr_account=_text(data.get("correspondent_account")),
        address=_text(_section(data, "address").get("value")),
    )


def _address(item: Mapping[str, Any]) -> AddressRecord:
    short = _text(item.get("value"))
    return AddressRecord(short=short, full=_text(item.get("unrestricted_value")) or short)


class DadataClient:
    def __init__(
        self, cfg: DadataConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._cfg = cfg
        self._http = httpx.AsyncClient(timeout=cfg.timeout_seconds, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _suggest(self, kind: str, query: str, count: int) -> list[Mapping[str, Any]]:
        try:
            response = await self._http.post(
                f"{self._cfg.api_url}/suggest/{kind}",
                headers={
                    "Authorization": f"Token {self._cfg.api_key}",
                    "Accept": "application/json",
                },
                json={"query": query, "count": count},
            )
        except httpx.HTTPError as exc:
            raise SuggestUnavailableError(
                f"DaData недоступна: {type(exc).__name__} {exc}".rstrip()
            ) from exc
        if response.status_code != 200:
            # 401/403 — ключ неверный или выключен, 429 — кончился дневной лимит:
            # человеку всё равно, он заполняет руками, причина — в лог.
            raise SuggestUnavailableError(f"DaData ответила {response.status_code}")
        try:
            items = response.json().get("suggestions")
        except ValueError as exc:
            raise SuggestUnavailableError("DaData ответила не JSON") from exc
        if not isinstance(items, list):
            raise SuggestUnavailableError("В ответе DaData нет списка suggestions")
        return [item for item in items if isinstance(item, Mapping)]

    async def companies(self, query: str, *, count: int) -> list[CompanyRecord]:
        return [_company(item) for item in await self._suggest("party", query, count)]

    async def banks(self, query: str, *, count: int) -> list[BankRecord]:
        return [_bank(item) for item in await self._suggest("bank", query, count)]

    async def addresses(self, query: str, *, count: int) -> list[AddressRecord]:
        return [_address(item) for item in await self._suggest("address", query, count)]
