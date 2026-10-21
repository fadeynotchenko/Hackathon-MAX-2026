"""Подсказки реквизитов по реестрам: организация по названию или ИНН, банк по
названию или БИК, адрес по первым словам.

Подсказка — набор значений под ключи реквизитов (``inn``, ``bic``, ``address``):
мини-апп подставляет их в карточку или в поля стороны документа по префиксу,
как подстановку из профиля. Значения реестра не проверяются здесь заново —
их проверит сохранение карточки или документа теми же правилами, что и ввод руками.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from core.domain.exceptions import AppError
from core.logs import biz_warn
from core.suggest import SuggestClient, SuggestUnavailableError

logger = logging.getLogger(__name__)

# Короче DaData ищет по всему реестру и возвращает случайные совпадения.
MIN_QUERY_LENGTH = 2
# Предел DaData на длину запроса.
MAX_QUERY_LENGTH = 300
SUGGEST_COUNT = 7


class SuggestKind(StrEnum):
    COMPANY = "company"
    BANK = "bank"
    ADDRESS = "address"


@dataclass(frozen=True)
class RequisiteSuggestion:
    title: str
    subtitle: str
    values: Mapping[str, str]


def _filled(values: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value}


def _join(*parts: str) -> str:
    return " · ".join(part for part in parts if part)


async def suggest_requisites(
    kind: SuggestKind, query: str, *, client: SuggestClient | None
) -> list[RequisiteSuggestion]:
    if client is None:
        raise AppError(
            "Поиск по реестру выключен, заполните поля вручную",
            code="suggest.unavailable",
            status_code=503,
        )
    text = " ".join(query.split())[:MAX_QUERY_LENGTH]
    if len(text) < MIN_QUERY_LENGTH:
        return []
    try:
        if kind is SuggestKind.COMPANY:
            return [
                RequisiteSuggestion(
                    title=company.name,
                    subtitle=_join(
                        f"ИНН {company.inn}" if company.inn else "", company.address, company.status
                    ),
                    values=_filled(
                        {
                            "name": company.name,
                            "inn": company.inn,
                            "kpp": company.kpp,
                            "ogrn": company.ogrn,
                            "address": company.address,
                            "director": company.director,
                        }
                    ),
                )
                for company in await client.companies(text, count=SUGGEST_COUNT)
            ]
        if kind is SuggestKind.BANK:
            return [
                RequisiteSuggestion(
                    title=bank.name,
                    subtitle=_join(f"БИК {bank.bic}" if bank.bic else "", bank.address),
                    values=_filled(
                        {"bank": bank.name, "bic": bank.bic, "corr_account": bank.corr_account}
                    ),
                )
                for bank in await client.banks(text, count=SUGGEST_COUNT)
            ]
        return [
            RequisiteSuggestion(
                title=address.short,
                subtitle=address.full if address.full != address.short else "",
                values={"address": address.full},
            )
            for address in await client.addresses(text, count=SUGGEST_COUNT)
            if address.full
        ]
    except SuggestUnavailableError as exc:
        biz_warn(logger, "suggest.failed", kind=kind.value, error=str(exc))
        raise AppError(
            "Поиск по реестру не отвечает, заполните поля вручную",
            code="suggest.unavailable",
            status_code=503,
            log_message=str(exc),
        ) from exc
