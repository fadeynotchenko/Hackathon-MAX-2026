# Деплой

Прод — один хост с Docker и compose-плагином, стек `docker-compose.prod.yml`,
выкатка скриптом `deploy.sh`. Управление — консоль `./maxapp --prod`.

## Первый запуск

1. Клонировать репозиторий, например в `/opt/maxapp`.
2. `cp .env.example .env` и заполнить. Обязательные переменные (реестр
   `core.config.env_spec`, `required_for`):
   - `MAX_BOT_TOKEN` — токен от MasterBot; он же подписывает initData мини-аппа;
   - `JWT_SECRET` — 32+ случайных символа (`openssl rand -hex 32`);
   - `DB_USER`, `DB_PASSWORD`, `DB_NAME` — Postgres в контейнере `db`;
   - `REDIS_PASSWORD` — Redis в контейнере `redis`;
   - `DOMAIN` — публичное имя стенда для `server_name` nginx;
   - `PUBLIC_BASE_URL` — `https://<DOMAIN>`, нужен боту в режиме webhook;
   - `BOT_WEBHOOK_SECRET` — 16+ символов, MAX присылает его в заголовке вебхука.
     Остальное имеет дефолты (`ENV=production` и `BOT_MODE=webhook` compose выставляет
     сам). Плейсхолдеры `dev-only-*` из `.env.example` в production отвергаются на старте.
3. Сертификаты: `gateway/ssl/fullchain.pem` и `privkey.pem`. Если их нет, `deploy.sh`
   поставит самоподписанную пару на 30 дней, чтобы gateway поднялся; настоящий
   сертификат выпускается через ACME по webroot `gateway/acme/` уже на работающем
   gateway (см. `gateway/ssl/README.md`).
4. `./deploy.sh` — создаст каталоги `app_logs/{api,bot,nginx}` и `backups/` с
   владельцами под uid контейнеров, соберёт образы, прогонит тесты в образе, поднимет
   стек и дождётся healthcheck'ов; миграции api применит сам при старте (advisory-lock
   защищает от гонки воркеров).
5. Проверка: `./maxapp --prod health`, `./maxapp --prod logs bot`. Бот при старте
   в режиме webhook сам регистрирует подписку в MAX на `PUBLIC_BASE_URL + BOT_WEBHOOK_PATH`.

## Доступ для проверяющих

HTTP-проверки (`DATA-API.yaml`, роль `user`) идут с долгим токеном отдельной
учётки: обычный access-токен живёт 15 минут, а initData без клиента MAX не
получить. Выпуск и отзыв — внутри контейнера api:

```bash
docker compose -f docker-compose.prod.yml exec api python -m core.scripts.issue_reviewer_token --days 14
docker compose -f docker-compose.prod.yml exec api python -m core.scripts.issue_reviewer_token --revoke
```

Срок — до 30 дней. Отзыв удаляет учётку с её документами. Чтобы проверяющим
доставлялись файлы в чат, выпускайте токен на настоящий MAX-id: `--max-user-id`.

## Обновление

```bash
./deploy.sh
```

Шаги: `git pull --ff-only` → тесты core в образе `core/Dockerfile --target test` (красные =
стоп; `SKIP_TESTS=1` пропускает, только если они зелёные в CI) → каталоги и TLS →
снимок БД `backups/predeploy_<дата>.dump` (хранится `PREDEPLOY_KEEP`, файлы `0600`) →
`docker compose up -d --build --remove-orphans --wait` → сводка, health, чистка старых
слоёв. Изменения в `.env` вносятся до запуска: контейнеры перечитают его при
пересоздании. `PREDEPLOY_KEEP` и `SKIP_TESTS` читаются из окружения shell, не из `.env`.

## Сервисы прод-стенда

| Сервис      | Образ                | Роль                                                                            |
| ----------- | -------------------- | ------------------------------------------------------------------------------- |
| `db`        | postgres:17-alpine   | БД, порт только на 127.0.0.1                                                    |
| `redis`     | redis:7-alpine       | сессии бота, стримы событий; AOF, пароль обязателен                             |
| `api`       | Dockerfile (runtime) | uvicorn, `API_WORKERS` воркеров                                                 |
| `bot`       | bot/Dockerfile       | бот, webhook на `bot:8080`, health `:8081`                                      |
| `gateway`   | gateway/Dockerfile   | TLS, статика мини-аппа (web), `/api/` → api, `${BOT_WEBHOOK_PATH}` → bot        |
| `db_backup` | postgres:17-alpine   | суточный `pg_dump` в `backups/` в `DB_BACKUP_HOUR_UTC`, хранит `DB_BACKUP_KEEP` |

`api` и `bot` работают с read-only FS, `tmpfs /tmp`, `cap_drop ALL`, `no-new-privileges`
и лимитами памяти и pids; `db`, `redis` и `gateway` — с точечными `cap_add` под свои
entrypoint'ы и `no-new-privileges`; `db_backup` получает только переменные дампа.
`API_WORKERS` по умолчанию 1: файл-лог не умеет ротироваться из нескольких
процессов; для большего числа воркеров задайте `LOG_DIR=` (пусто) и читайте логи
из docker stdout.

## Бэкапы и откат

- Суточные дампы: `backups/<DB_NAME>_<дата>.dump` + `.sha256`.
- Снимок перед выкаткой: `backups/predeploy_<дата>.dump`.
- Восстановление (при остановленных `api` и `bot`, иначе блокировки):
  `docker compose -f docker-compose.prod.yml stop api bot`, затем
  `docker compose -f docker-compose.prod.yml exec -T db pg_restore -U $DB_USER -d $DB_NAME --clean --if-exists < backups/<файл>.dump`,
  затем `./deploy.sh`.
- Откат кода: `git checkout <ревизия> && ./deploy.sh` (миграции вниз — `alembic downgrade -1` внутри контейнера api при необходимости).

## Логи на сервере

`app_logs/` (bind-mount, по подкаталогу на сервис): `api/api.log`, `bot/bot.<дата>.N.log`,
`nginx/access-<дата>.log` (gateway). Живой хвост —
`./maxapp --prod logs <сервис>`. Формат и корреляция — `docs/LOGGING.md`.

## Dev-стенд

`docker compose up --build`: пять контейнеров (`db`,
`redis`, `api`, `bot`, `web`), исходники смонтированы, core с `--reload`, бот через
`tsx watch`, мини-апп через vite с HMR на `:3090` (порты задаются в `.env`, группа
«Порты на хосте»). Gateway в dev не поднимается: vite сам проксирует `/api/`. Зависимости Node ставит
одноразовый сервис `deps`, `bot` и `web` ждут его. Бот в dev работает polling'ом:
публичный адрес не нужен. Чтобы открыть мини-апп из настоящего MAX-клиента, поднимите
туннель на `localhost:3090` (`allowedHosts` у vite открыт) и укажите его адрес как URL
мини-аппа в MasterBot. Dev-вход включается переменной `DEV_LOGIN_ENABLED=true`
(dev-compose ставит её сам; в production запрещена).
