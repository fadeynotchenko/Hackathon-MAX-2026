# MAX mini app

Фундамент мини-приложения для мессенджера MAX. Репозиторий один, сервисов
четыре, и каждая папка в корне — отдельная деплой-единица со своим рантаймом:

```
core/       Python: API мини-аппа, миграции, потребитель событий бота; владелец PostgreSQL
bot/        Node: бот MAX (@maxhub/max-bot-api), доставка уведомлений
web/        React + Vite: мини-апп, вход через window.WebApp.initData
gateway/    nginx (только прод): TLS, /api/ → core, /bot/webhook → bot, статика web
contracts/  OpenAPI core и схема событий — единственное общее между сервисами
docs/       архитектура, деплой, логи, платформа MAX
```

Сейчас всё едет одним compose-стеком; вынос любого сервиса на свой хост —
перенос его блока в другой compose. Правила и карта модулей —
[AGENTS.md](AGENTS.md); архитектура — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md);
деплой — [docs/DEPLOY.md](docs/DEPLOY.md); логи — [docs/LOGGING.md](docs/LOGGING.md);
платформа MAX — [docs/MAX_PLATFORM.md](docs/MAX_PLATFORM.md).

## Быстрый старт

Нужны Docker с compose, `uv` и Node 24 (pnpm ставится через `npx`).

```bash
cp .env.example .env      # MAX_BOT_TOKEN от MasterBot, JWT_SECRET, DB_PASSWORD, REDIS_PASSWORD
docker compose -f docker-compose.dev.yml up --build
```

| Адрес                               | Что                                              |
| ----------------------------------- | ------------------------------------------------ |
| http://localhost:3090               | мини-апп (vite с HMR; /api/ проксируется в core) |
| http://localhost:3090/api/v1/docs   | Swagger API                                      |
| http://localhost:3090/api/v1/health | health core (БД, Redis, воркер событий)          |

Dev-стенд — пять контейнеров: `db`, `redis`, `api`, `bot`, `web` (плюс одноразовый
`deps` для установки Node-зависимостей). Мини-апп в браузере входит сам тестовым
пользователем: ручка `/api/v1/dev/init-data` включается `DEV_LOGIN_ENABLED=true`
(dev-compose ставит сам, в production запрещена). Бот работает через polling, публичный адрес не нужен,
но нужен настоящий `MAX_BOT_TOKEN`: с плейсхолдером он получает 401 от MAX.
Для production-сборки в браузере — подписанный dev-initData:

```bash
cd core && uv run python -m core.scripts.dev_init_data --user-id 1 --first-name Dev   # → VITE_DEV_INIT_DATA для .env
```

Локально без Docker (нужны Postgres и Redis рядом):

```bash
cd core && uv sync && uv run alembic upgrade head && uv run uvicorn core.api.main:app --reload
npx -y pnpm@12.4.2 install
npx -y pnpm@12.4.2 --filter @maxapp/bot dev      # бот
npx -y pnpm@12.4.2 --filter @maxapp/web dev      # мини-апп :3000 (проксирует /api/ в :8000)
# Порты docker-стенда (3090/8091/5490/6490) выбраны так, чтобы не пересекаться с другими проектами; меняются в .env.
```

## Проверки

Одной командой — `./maxapp check` (ruff, import-linter, pytest в `core/`;
eslint, tsc, dependency-cruiser, vitest в `bot/` и `web/`). По отдельности:

```bash
cd core && uv run pytest -q && uv run ruff check . && uv run lint-imports
npx -y pnpm@12.4.2 lint && npx -y pnpm@12.4.2 typecheck && npx -y pnpm@12.4.2 test
```

Pre-commit: `cd core && uv run pre-commit install --config ../.pre-commit-config.yaml`. Claude Code: хуки в `.claude/` прогоняют линтеры на
каждую правку и контракты в конце хода.

## Консоль стенда

```bash
./maxapp                 # интерактивно: /logs, /ps, /health, /psql, /redis, /migrate, /check
./maxapp logs api        # разово
./maxapp --prod ps       # прод-стенд (docker-compose.prod.yml)
```

## Прод

На сервере: `.env`, сертификаты в `gateway/ssl/`, затем `./deploy.sh` — прогон
тестов core в образе, снимок БД, `docker compose -f docker-compose.prod.yml up -d --build`.
Прод-стенд — шесть контейнеров: `db`, `redis`, `api`, `bot`, `gateway`, `db_backup`;
миграции api применяет сам при старте.
Подробности и список обязательных переменных — [docs/DEPLOY.md](docs/DEPLOY.md).
