---
description: Сверить README/AGENTS/CLAUDE/docs с кодом и обновить устаревшее
---

Проверь, что документация соответствует коду, и обнови расхождения:

1. Прогони `cd core && uv run pytest tests/repo -q`: замки сверяют сервисы compose,
   env-реестр, схемы событий и OpenAPI с документацией.
2. Перечитай `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOY.md`,
   `docs/LOGGING.md`, `docs/MAX_PLATFORM.md` и сверь с текущими файлами: структура каталогов,
   команды, переменные окружения, сервисы compose, имена событий, эндпоинты API.
3. Регенерируй артефакты из `core/`: `uv run python -m core.scripts.gen_env_example`,
   `uv run python -m core.scripts.export_openapi` (затем из корня
   `npx -y pnpm@12.4.2 --filter @maxapp/web gen:api`), `uv run python -m core.scripts.export_event_schemas`.
4. Исправь текст документов там, где он отстал. Формулировки короткие, без маркеров генерации.

В конце перечисли, что изменилось.
