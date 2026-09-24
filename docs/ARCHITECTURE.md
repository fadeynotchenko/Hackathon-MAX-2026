# Архитектура

Репозиторий один, сервисов четыре: `core`, `bot`, `web`, `gateway`. Сейчас они
едут одним compose-стеком (модульный монолит), но границы между ними уже
микросервисные: разные рантаймы, свои образы и healthcheck, никаких импортов
друг из друга. Общее — только `contracts/` и инфраструктура. Правила проверяются
машинно, поэтому документ описывает то, что не пройдёт линтер, а не пожелания.

## Сервисы и границы

```
  MAX ──webhook/polling──▶ bot (Node) ──XADD──▶ Redis Stream to_core ──▶ core: api (воркер событий) ──▶ Postgres
                             ▲                                              │
                             └──XREADGROUP── Redis Stream to_bot ◀──XADD────┤ (ответы помощника, document.ready)
                                                                            ├──▶ хранилище MAX (фото и голосовые по ссылке)
                                                                            └──▶ GigaChat (модель, распознавание)

  MAX-клиент ──initData──▶ web (React, статика) ──/api/v1──▶ gateway (nginx) ──▶ core: api ──▶ Postgres, Redis
```

Вложение, присланное боту, едет по шву ссылкой (`bot.attachment`), а не байтами:
стрим — не файловое хранилище, файл ядро скачивает само (`core.files.inbound`).

| Граница       | Контракт                                                                                                  | Где проверяется                                              |
| ------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| core ↔ web    | OpenAPI: `contracts/openapi.json` → `web/src/api/schema.d.ts`                                             | `core/tests/repo/test_generated_artifacts.py`, компилятор TS |
| core ↔ bot    | Схема событий: `core.events.contracts` → `contracts/events.schema.json` → zod в `bot/src/events/codec.ts` | тот же замок + `bot/src/events/codec.test.ts`                |
| bot ↔ gateway | HTTP-вебхук MAX на `${BOT_WEBHOOK_PATH}` с секретом в заголовке                                           | `bot/src/main.ts` (SDK проверяет секрет)                     |

Запреты: `bot/src` и `web/src` не импортируют `core/` и друг друга
(`.dependency-cruiser.cjs`: `services-share-only-contracts`, `bot-and-web-independent`);
Python в core импортирует только пакет `core` (`import-linter`, `root_package = core`);
образ core собирается из `./core` и физически не видит другие сервисы
(`core/tests/repo/test_docs_sync.py::test_core_build_context_is_isolated`).

## Слои core

```
               ┌─────────────┐                 транспорт и запуск: роутеры, middleware,
               │    api/     │                 lifespan (миграции, воркер событий)
               └──────┬──────┘                 парсит вход → зовёт сценарий → рендерит
                      ▼
               ┌─────────────┐                 use-case-ы: auth, users, documents, agent
               │  usecases/  │                 функции с явными session/cfg/now,
               └──────┬──────┘                 результат — frozen dataclass
     ┌──────────┬─────┴────┬──────────┐
     ▼          ▼          ▼          ▼
┌─────────┐┌─────────┐┌─────────┐┌─────────┐  events — шов с ботом (Redis Streams);
│ events/ ││   db/   ││ files/  ││  llm/   │  db — модели, репозитории, движок, Redis;
└────┬────┘└────┬────┘└────┬────┘└────┬────┘  files — DOCX, PDF, хранение, вложения;
     └──────────┴────┬─────┴──────────┘       llm — порт модели (с вложениями) и GigaChat
                     ▼                        друг о друге не знают
               ┌─────────────┐                 структурированные логи
               │    logs/    │
               └──────┬──────┘
              ┌───────┴────────┐
              ▼                ▼
        ┌───────────┐    ┌───────────┐         config — env-реестр и конфиги;
        │  config/  │    │  domain/  │         domain — чистый домен без I/O
        └───────────┘    └───────────┘         (initData, поля, типы файлов, исключения)
```

Контракт `layers` в `core/pyproject.toml` (`[tool.importlinter]`): верхний слой
может импортировать любой нижний, слои через `|` независимы. `scripts/` —
инструменты разработчика, вне контракта. Проверка: `cd core && uv run lint-imports`,
тот же вызов в pre-commit, Stop-хуке Claude Code и `core/tests/repo/test_import_contracts.py`.

Слои по именам: `api`, `usecases`, `events`, `db`, `files`, `llm`, `logs`, `config`, `domain`.

## Где живут модели

Четыре вида «моделей» — это разные роли, не дубли:

| Что                              | Где                                         | Жизненный цикл                                      |
| -------------------------------- | ------------------------------------------- | --------------------------------------------------- |
| `MaxUser`, `InitData`            | `core.domain.initdata`                      | подписанный payload платформы; форма задана MAX     |
| `User`, `RefreshToken`, `JobRun` | `core.db.models`                            | персистентность; форма задана миграциями            |
| `UserUpsert`                     | `core.db.repositories.user_repository`      | команда записи: что обновлять при конфликте         |
| `UserProfile`, `IssuedSession`   | `core.usecases.users`, `core.usecases.auth` | выход сценария: то, что можно показать наружу       |
| `NotifyUser`, `BotUserStarted`   | `core.events.contracts`                     | payload событий; их схема уезжает в `contracts/`    |
| `UserProfileSchema` и прочие     | `core.api.schemas`                          | wire-контракт OpenAPI; из него генерируются TS-типы |

Граница `usecases → api` проходит по dataclass-результатам: ORM-объект в роутер
не попадает, поэтому ленивая загрузка вне сессии невозможна по построению.

## Протокол потребителя событий

Обе стороны (Python `core.events.bus.consume_stream`, запускаемый из `core.api.events_worker`;
TS `bot/src/events/consumer.ts`)
реализуют один цикл: XAUTOCLAIM зависших у упавших потребителей → XREADGROUP
новых → обработчик → XACK. Конверт `{id, v, type, payload, ts, source}`. Битый
конверт, невалидный payload и отказ домена подтверждаются сразу (повтор не
поможет); временная ошибка остаётся pending и переигрывается до `max_deliveries`,
после чего подтверждается с записью `events.handler.dropped`.

Потребитель ядра обрабатывает события параллельно (до `WORKER_CONCURRENCY`), но
с ключом очереди `max_user_id`: реплики одного пользователя идут строго друг за
другом, разных — одновременно, и распознавание чужого фото не задерживает ответ.
События в работе «продлеваются» (`XCLAIM … JUSTID` сбрасывает простой, не трогая
счётчик доставок), поэтому долгий вызов модели не выглядит зависшим для соседнего
процесса; зависшие у упавших забираются `XAUTOCLAIM … JUSTID`, а повтором
(`XCLAIM`, счётчик +1) становятся только те, что никто не обрабатывает.

## TS-контракты (`.dependency-cruiser.cjs`)

- `bot/src` и `web/src` не импортируют `core/` и друг друга.
- В боте `config`, `logger`, `session`, `events`, `health` не импортируют `handlers`
  и `keyboards`: зависимости направлены от сценариев к инфраструктуре.
- В мини-аппе `src/max` (мост WebApp) — лист; `src/api` не знает о React-дереве.
- Циклы запрещены, dev-зависимости в прод-коде запрещены.
