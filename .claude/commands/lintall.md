---
description: Полный локальный quality-gate (ruff, lint-imports, eslint, tsc, depcruise, core/tests/repo) и починка
---

Прогони полный набор проверок и почини всё красное, по порядку:

1. `cd core && uv run ruff check . && uv run ruff format --check .`
2. `cd core && uv run lint-imports --cache-dir .cache/import-linter` (контракты слоёв core)
3. `npx -y pnpm@12.4.2 lint` (eslint) и `npx -y pnpm@12.4.2 typecheck` (tsc обоих воркспейсов)
4. `npx -y pnpm@12.4.2 depcruise` (контракты TS: bot ⊥ web ⊥ core)
5. `cd core && uv run pytest tests/repo -q` (замки репозитория: env-реестр, документация, compose, маркеры)

Это те же проверки, что в pre-commit и в `./maxapp check`. Каждое падение чини в первопричине
и перезапускай упавший шаг до зелёного. В конце коротко сообщи статус всех пяти шагов.
Коммит и push только по явной просьбе.
