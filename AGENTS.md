# MAX mini app — канон проекта

Фундамент мини-приложения для мессенджера MAX. Репозиторий один, но каждая
папка в корне — отдельный сервис со своим рантаймом, образом и healthcheck:
сейчас они едут одним compose-стеком, завтра любой из них уезжает на свой хост
или в свой репозиторий без переписывания. Этот файл — единый источник правил
для людей и агентов (Claude Code подключает его через `CLAUDE.md`). Документ
проверяется тестами `core/tests/repo/test_docs_sync.py`: устаревший абзац
валит прогон, а не ждёт, пока его заметят.

## Сервисы

| Папка        | Рантайм                              | Роль                                                                                           |
| ------------ | ------------------------------------ | ---------------------------------------------------------------------------------------------- |
| `core/`      | Python 3.14, FastAPI, uv             | API мини-аппа, миграции при старте, потребитель событий бота; единственный владелец PostgreSQL |
| `bot/`       | Node 24, `@maxhub/max-bot-api`, pnpm | Бот MAX: приветствие, кнопка мини-аппа, доставка уведомлений из core                           |
| `web/`       | React 19, Vite, pnpm                 | Мини-апп; собирается в статику, которую отдаёт gateway                                         |
| `gateway/`   | nginx                                | TLS, маршрутизация `/api/` → core, `${BOT_WEBHOOK_PATH}` → bot, статика web, rate limits, CSP  |
| `contracts/` | JSON                                 | То единственное, что сервисы разделяют: OpenAPI core и схема событий                           |
| `docs/`      | Markdown                             | Архитектура, деплой, логи, платформа MAX                                                       |

Инфраструктура общая на стек: PostgreSQL (только core), Redis (сессии бота,
стримы событий). Корень: `docker-compose.{dev,prod,test}.yml`, `deploy.sh`,
консоль `./maxapp`, pnpm-воркспейсы (`package.json`, `pnpm-workspace.yaml`),
общие конфиги линтеров (`eslint.config.js`, `prettier.config.js`,
`.dependency-cruiser.cjs`), `.pre-commit-config.yaml`, `.env.example`.

## Инварианты

1. **Сервисы не импортируют друг друга.** Общее — только `contracts/` и
   инфраструктура. Проверяется машинно: `.dependency-cruiser.cjs`
   (`services-share-only-contracts`, `bot ⊥ web`), `import-linter` с
   `root_package = core` (Python видит только свой пакет) и замок
   `test_core_build_context_is_isolated` (образ core собирается из `./core`
   и не может скопировать чужие файлы).
2. **Внутри core направление зависимостей одностороннее:**
   `api → usecases → events | db → logs → config | domain`.
   Контракт `layers` в `core/pyproject.toml` (`[tool.importlinter]`), проверка
   `lint-imports`. В TS: инфраструктура бота (`config`, `logger`, `session`,
   `events`, `health`) не импортирует `handlers`/`keyboards`; в web `src/max`
   и `src/api` не знают о React-дереве.
3. **Доступ к БД только через `core.db.repositories`.** ORM-объекты не покидают
   `core.usecases`: наружу уходят frozen dataclass-результаты (`UserProfile`,
   `IssuedSession`), в API — pydantic-схемы из `core.api.schemas`.
4. **Сценарии каналонейтральны.** Функция из `core.usecases` одинаково
   вызывается из роутера и из потребителя событий, принимает `AsyncSession` и конфиг явно,
   бросает `core.domain.exceptions.AppError`, не `HTTPException`. Маппинг на
   HTTP — `core.api.error_handlers`.
5. **Окружение читается в одном месте.** Python — `core.config.env`, бот —
   zod-схема `bot/src/config.ts`. Каждая переменная стека описана в реестре
   `core.config.env_spec`; корневой `.env.example` генерируется из него
   (`cd core && uv run python -m core.scripts.gen_env_example`), тест-замок
   ловит дрейф.
6. **Шов core↔bot — Redis Streams с типизированным контрактом.** Payload описан
   pydantic-моделями в `core.events.contracts`, JSON Schema экспортируется в
   `contracts/events.schema.json`, zod-схемы бота сверяются с ней тестом.
   Потребители идемпотентны по `Event.id`; окончательные ошибки подтверждаются
   сразу, временные переигрываются до предела доставок.
7. **Вход мини-аппа только по подписи initData** (`core.domain.initdata`).
   Access-JWT живёт в памяти клиента, refresh — в httpOnly-cookie (`SameSite=None;
Secure` в проде: веб-клиент MAX держит мини-апп во фрейме) с атомарной ротацией
   и отзывом семьи при повторном использовании; отзыв коммитится до ответа 401.
   Ручки, работающие по cookie, отвергают `Sec-Fetch-Site: cross-site`.
8. **Логи — структурированные события** `<домен>.<действие>` через `core.logs`
   и pino, одна JSON-схема; `request_id` сшивает gateway, core и жалобу пользователя.
9. **Схемой БД владеют миграции Alembic**, не `create_all`. Правка
   `core.db.models` = новая ревизия в `core/src/core/db/migrations/versions/`.
   Миграции применяет сам процесс api при старте (`core.db.migrate`,
   advisory-lock против гонки воркеров); отдельного контейнера для них нет.
10. **Git** — commit и push только по явной просьбе владельца. Перед сдачей
    работы все проверки зелёные (`./maxapp check`).
11. **Никаких каталогов «на будущее».** Новый пакет появляется вместе с кодом,
    который в нём живёт, и тестом, который его проверяет.

## Код и комментарии

- Идентификаторы по-английски, комментарии и документация по-русски.
- Комментарий объясняет **почему**, а не пересказывает код: ограничение
  платформы, инцидент, отвергнутая альтернатива. Если «почему» нет —
  комментария тоже нет.
- Без маркеров сгенерированного текста: обращений к читателю, эмодзи,
  заголовков-разделителей вроде «imports» или «step 1», заглушек «insert here»,
  TODO без номера задачи. Список запрещённых шаблонов —
  `core/tests/repo/ai_markers.txt`, тест `test_no_ai_markers.py` сканирует
  репозиторий целиком.
- Каждый модуль начинается с docstring/комментария о его роли и границах.
- Тест пишется вместе с кодом: новая ручка API, сценарий, обработчик события,
  экран мини-аппа — с тестом рядом (`core/tests/<пакет>/`, `*.test.ts`).

## Сервис core

Пакет `core/src/core/` (устанавливается editable через `uv sync`), тесты в
`core/tests/` по пакетам плюс `core/tests/repo/` — замки на весь репозиторий.

| Пакет       | Роль                                                                                                                                                                                                                                                                                                             |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api/`      | FastAPI: `main.py` (`create_app`, lifespan: миграции, воркер событий), `routers/` (в том числе `dev.py` — dev-вход только вне production), `schemas/`, `middlewares/` (request-id и access-лог, таймаут), `error_handlers.py`, `dependencies.py`, `state.py`, `events_worker.py` (потребитель стрима bot → core) |
| `usecases/` | Сценарии: `auth/` (вход по initData, выдача и ротация сессии), `users/` (профиль, синхронизация из бота)                                                                                                                                                                                                         |
| `events/`   | Контракты событий и шина Redis Streams (`bus.py`: publish, consume с XAUTOCLAIM/XACK)                                                                                                                                                                                                                            |
| `db/`       | `models.py`, `repositories/`, `base.py` (движок), `redis.py`, `config.py`, `types.py`, `migrate.py` (upgrade при старте), `migrations/`                                                                                                                                                                          |
| `logs/`     | Структурированные логи: `setup.py` (JSON/pretty, посуточная ротация), `bizlog.py`                                                                                                                                                                                                                                |
| `config/`   | `env.py` (единственное чтение окружения), `env_spec.py` (реестр стека), `app_config.py`                                                                                                                                                                                                                          |
| `domain/`   | Чистый домен без I/O: `exceptions.py`, `initdata.py` (подпись MAX)                                                                                                                                                                                                                                               |
| `scripts/`  | Генераторы артефактов: `gen_env_example`, `export_openapi`, `export_event_schemas`, `dev_init_data`                                                                                                                                                                                                              |

Корень `core/`: `pyproject.toml` (зависимости, ruff, pytest, import-linter),
`uv.lock`, `alembic.ini`, `Dockerfile` (targets `runtime`/`test`).

## Фоновая работа внутри api

Отдельных контейнеров-воркеров нет: для хакатона они лишние, а каждый —
это ещё один процесс, healthcheck и точка отказа.

- Миграции: `core.db.migrate.upgrade_to_head` в lifespan до открытия пула;
  несколько воркеров uvicorn сериализуются `pg_advisory_xact_lock` в
  `migrations/env.py`. Вручную — `./maxapp migrate`.
- Потребитель событий бота: `core.api.events_worker` читает
  `EVENTS_STREAM_TO_CORE` в consumer group `core` (каждый воркер uvicorn — свой
  consumer), `bot.user_started` → `core.usecases.users.register_user_from_bot`.
  Состояние задачи видно в `/health` полем `events_worker`.

Периодические задачи (чистка, отчёты) при необходимости добавляются так же —
фоновой задачей в lifespan; отдельный контейнер заводится, когда задача
начинает мешать API по CPU или памяти.

## События

Контракты — `core.events.contracts`, версия конверта `ENVELOPE_VERSION`,
схема — `contracts/events.schema.json`.

- `notify.user` (core → bot, `EVENTS_STREAM_TO_BOT`): `max_user_id`, `text`,
  `format` (`markdown` | `html` | null). Публикует `EventBus.notify_user`
  (ручка `POST /api/v1/admin/notify` возвращает UUID события). Бот помнит
  доставленные `Event.id` в Redis (`events:delivered:*`), поэтому повторная
  доставка не даёт дубля сообщения.
- `bot.user_started` (bot → core, `EVENTS_STREAM_TO_CORE`): `max_user_id`,
  `chat_id`, `first_name`, `last_name`, `username`, `language_code`,
  `start_payload`. Публикует бот на `bot_started` и `/start`; читает воркер
  внутри api.

Добавить событие: модель в `contracts.py` и запись в `EVENT_PAYLOADS` →
`uv run python -m core.scripts.export_event_schemas` → zod-схема в
`bot/src/events/codec.ts` (тест `codec.test.ts` сверит со схемой) →
обработчик на принимающей стороне → абзац здесь.

## API

Префикс `/api/v1`, OpenAPI экспортируется в `contracts/openapi.json`, TS-типы —
`web/src/api/schema.d.ts` (`pnpm --filter @maxapp/web gen:api`). Ошибки всегда
`{"detail", "code", "request_id"}`.

| Метод | Путь             | Что делает                                                                          |
| ----- | ---------------- | ----------------------------------------------------------------------------------- |
| GET   | `/health`        | Проверка БД, Redis и воркера событий; 503 при деградации                            |
| POST  | `/auth/max`      | Вход по `init_data`; ставит refresh-cookie, отдаёт access-токен и профиль           |
| POST  | `/auth/refresh`  | Ротация refresh-cookie, новый access-токен                                          |
| POST  | `/auth/logout`   | Отзыв семьи refresh-токена, очистка cookie                                          |
| GET   | `/me`            | Профиль текущего пользователя (Bearer)                                              |
| GET   | `/admin/stats`   | Сводка: пользователи, активность за сутки (админ)                                   |
| POST  | `/admin/notify`  | Сообщение пользователю через бота (админ), 202 + UUID события                       |
| GET   | `/dev/init-data` | initData тестового пользователя; только при `DEV_LOGIN_ENABLED=true` вне production |

Новая ручка: роутер в `core.api.routers`, схемы в `core.api.schemas`, сценарий в
`core.usecases`, тест в `core/tests/api/`, затем экспорт OpenAPI и `gen:api`,
строка в таблице выше.

## Бот и мини-апп

- `bot/src`: `main.ts` (polling | webhook, health-сервер, graceful shutdown),
  `config.ts` (zod), `logger.ts` (pino), `redis.ts`, `context.ts`,
  `session/redis-store.ts`, `events/` (`codec.ts`, `consumer.ts`, `publisher.ts`,
  `handlers.ts`), `handlers/`, `keyboards/`, `middlewares/`, `health.ts`;
  `bot/certs/` — корень Минцифры для Bot API (`NODE_EXTRA_CA_CERTS`).
- `web/src`: `max/webapp.ts` (мост `window.WebApp`), `api/client.ts` (Bearer,
  refresh на 401, типы из `schema.d.ts`), `auth/` (контекст сессии, провайдер),
  `pages/`, `components/`, `styles/`.

## Команды

```bash
cd core && uv sync && cd ..              # Python-окружение сервиса core
npx -y pnpm@12.4.2 install               # Node-воркспейсы (bot, web)
cp .env.example .env                     # заполнить MAX_BOT_TOKEN, JWT_SECRET, пароли

./maxapp check                           # ruff, lint-imports, pytest, eslint, tsc, depcruise, vitest
cd core && uv run pytest -q              # только тесты core
npx -y pnpm@12.4.2 test                  # только vitest (bot + web)

docker compose -f docker-compose.dev.yml up --build   # dev-стенд: http://localhost:3090
./maxapp logs api                        # логи сервиса (или ./maxapp без аргументов — консоль)
./maxapp --prod deploy                   # на сервере: ./deploy.sh
```

Стек: Python 3.14, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, redis.asyncio,
PyJWT, uv, ruff, import-linter, pytest (aiosqlite + fakeredis); Node 24, TypeScript 5.9,
pnpm 12, `@maxhub/max-bot-api`, ioredis, pino, zod, React 19, Vite 8, vitest,
eslint (type-aware), prettier, dependency-cruiser; PostgreSQL 17, Redis 7, nginx 1.27.

## Вынос сервиса из монолита

| Сервис            | Что забирает          | Что нужно снаружи                                                  |
| ----------------- | --------------------- | ------------------------------------------------------------------ |
| `core`            | папку `core/` целиком | Postgres, Redis, `contracts/` как выход                            |
| `bot`             | `bot/` + pnpm-lock    | Redis, публичный https для webhook, `contracts/events.schema.json` |
| `web` + `gateway` | `web/`, `gateway/`    | адрес API (`VITE_API_BASE_URL`), `contracts/openapi.json`          |

Переезд на отдельный хост — перенос блока сервиса в другой compose и адреса
`DB_HOST`/`REDIS_HOST` в `.env`. Переезд в отдельный репозиторий — копия папки
сервиса и подписка на `contracts/` (git subtree или пакет).

## Память агента

Стабильные правила — здесь. Накопленный контекст (обоснования решений, разборы
инцидентов, нюансы платформы MAX) — в файловой памяти агента; перед задачей
перечитать её, после — обновить, если узнано что-то долговечное.
