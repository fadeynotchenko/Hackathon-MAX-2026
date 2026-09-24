"""Языковая модель: порт для сценариев и адаптер GigaChat.

Инфраструктурный слой рядом с ``db``, ``events`` и ``files``. Сценарии зависят
только от протокола ``LLMClient``; провайдер выбирается здесь, в одном месте.
"""

from .client import ChatMessage, LLMClient, LLMError, LLMUnavailableError
from .config import GigaChatConfig
from .gigachat import GigaChatClient


def build_llm_client(cfg: GigaChatConfig) -> LLMClient | None:
    """Без ключа агента нет: сценарии отвечают понятной ошибкой, а не подменяют модель."""
    return GigaChatClient(cfg) if cfg.enabled else None


__all__ = [
    "ChatMessage",
    "GigaChatClient",
    "GigaChatConfig",
    "LLMClient",
    "LLMError",
    "LLMUnavailableError",
    "build_llm_client",
]
