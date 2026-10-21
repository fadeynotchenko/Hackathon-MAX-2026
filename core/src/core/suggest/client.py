"""Порт подсказок по реестрам: организации, банки, адреса.

Сценарии знают только эти записи и протокол ``SuggestClient``; какой сервис
отвечает и как называются поля в его ответе, решает адаптер. Запись — то, что
реестр знает о найденном: пустая строка значит «в реестре нет», а не «пусто».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompanyRecord:
    name: str
    inn: str
    kpp: str
    ogrn: str
    address: str
    director: str
    # Только для подписи в списке: «ликвидирована» рядом с названием спасает от
    # договора с несуществующей фирмой. У действующей — пусто.
    status: str
    individual: bool


@dataclass(frozen=True)
class BankRecord:
    name: str
    bic: str
    corr_account: str
    address: str


@dataclass(frozen=True)
class AddressRecord:
    # Короткий вид — для строки списка, полный (с индексом и регионом) — в документ.
    short: str
    full: str


class SuggestUnavailableError(RuntimeError):
    """Сервис подсказок не ответил, ответил ошибкой или не пустил по ключу."""


class SuggestClient(Protocol):
    async def companies(self, query: str, *, count: int) -> list[CompanyRecord]: ...

    async def banks(self, query: str, *, count: int) -> list[BankRecord]: ...

    async def addresses(self, query: str, *, count: int) -> list[AddressRecord]: ...

    async def aclose(self) -> None: ...
