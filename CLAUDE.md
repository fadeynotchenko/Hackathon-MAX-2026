@AGENTS.md

## Инструменты Claude Code в этом репозитории

Конфигурация в `.claude/`:

- **Хуки** (срабатывают сами):
  - PostToolUse на правку файла → `.claude/hooks/lint-on-edit.sh`: `ruff --fix` + `ruff format`
    для `*.py` (окружение `core/.venv`), `prettier` + `eslint --fix` для `*.ts/*.tsx`,
    `prettier` для json/yaml/md/css. Неустранимые замечания возвращаются в ход.
  - Stop → `.claude/hooks/contracts-on-stop.sh`: при изменённых `.py`, compose, gateway,
    contracts или docs — `lint-imports` в `core/` и `pytest core/tests/repo`; при изменённых
    `.ts/.tsx` — `depcruise`. Нарушение блокирует завершение хода.
  - Следствие: форматирование и контракты гарантированы автоматически, а вот полный прогон
    тестов хуки не делают — для него `/test`.
- **Команды**: `/test` (pytest + vitest), `/lintall` (полный quality-gate), `/spike`
  (исследовательский документ), `/audit` (read-only аудит субагентом), `/docs-sync`
  (сверка документации с кодом и регенерация артефактов в `contracts/`).
- **Субагент** `maxapp-auditor` — аудит на баги, безопасность и нарушения архитектуры;
  код не меняет.
- **launch.json**: конфигурации `web` (vite :3000) и `api` (uvicorn из `core/`, :8000).

Перед сдачей работы: `./maxapp check` зелёный, документация сверена (`/docs-sync`),
коммит только по просьбе владельца.
