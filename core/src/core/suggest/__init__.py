"""Подсказки по реестрам: порт для сценариев и адаптер DaData.

Инфраструктурный слой рядом с ``llm``: сценарии зависят только от протокола
``SuggestClient``, провайдер выбирается здесь.
"""

from .client import (
    AddressRecord,
    BankRecord,
    CompanyRecord,
    SuggestClient,
    SuggestUnavailableError,
)
from .config import DadataConfig
from .dadata import DadataClient


def build_suggest_client(cfg: DadataConfig) -> SuggestClient | None:
    """Без ключа подсказок нет: ручка отвечает 503, поля заполняются руками."""
    return DadataClient(cfg) if cfg.enabled else None


__all__ = [
    "AddressRecord",
    "BankRecord",
    "CompanyRecord",
    "DadataClient",
    "DadataConfig",
    "SuggestClient",
    "SuggestUnavailableError",
    "build_suggest_client",
]
