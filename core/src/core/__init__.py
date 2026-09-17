"""Python-сервис core: API мини-аппа, миграции при старте, потребитель событий бота, владелец PostgreSQL.

Слои (сверху вниз): api → usecases → events | db → logs → config | domain.
Контракт в pyproject.toml ([tool.importlinter]) проверяется lint-imports.
"""
