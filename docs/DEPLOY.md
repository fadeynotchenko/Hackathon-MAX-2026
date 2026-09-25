# Деплой

Прод — один хост с Docker и compose-плагином, стек `docker-compose.prod.yml`,
выкатка скриптом `deploy.sh`. Управление — консоль `./maxapp --prod`.

Адрес стенда — `https://project-documents-max.ru`: он же указан URL мини-приложения
в MAX. Клиент MAX открывает мини-апп только по https с доверенным сертификатом,
а вебхук бота MAX доставляет на тот же домен, поэтому стенд должен быть доступен
из интернета постоянно: локальный `docker compose up` на ноутбуке для этого не
годится (см. «Домашний компьютер вместо сервера»).

## Что нужно заранее

- Сервер с публичным IPv4 и Docker с compose-плагином: 2 CPU, 4 ГБ памяти, 20 ГБ
  диска (под такой хост настроены лимиты контейнеров и Postgres). Образы берутся с
  Docker Hub: если `docker pull` на сервере не проходит, подключите зеркало реестра
  (`registry-mirrors` в `/etc/docker/daemon.json`), которое даёт хостинг.
- A-запись домена у регистратора: `project-documents-max.ru → <IP сервера>`
  (AAAA — только если IPv6 у сервера настоящий, иначе удалите её: Let's Encrypt
  проверяет домен и по IPv6). Проверка: `dig +short project-documents-max.ru`
  отвечает IP сервера.
- Входящие порты 80 и 443 открыты в файрволе сервера и в панели хостинга: 80 нужен
  Let's Encrypt для проверки домена и редиректа на https, 443 — мини-аппу и вебхуку.

## Первый запуск

1. Клонировать репозиторий, например в `/opt/maxapp`.
2. `cp .env.example .env` и заполнить. Обязательные переменные (реестр
   `core.config.env_spec`, `required_for`):
   - `MAX_BOT_TOKEN` — токен от MasterBot; он же подписывает initData мини-аппа;
   - `JWT_SECRET` — 32+ случайных символа (`openssl rand -hex 32`);
   - `DB_USER`, `DB_PASSWORD`, `DB_NAME` — Postgres в контейнере `db`;
   - `REDIS_PASSWORD` — Redis в контейнере `redis`;
   - `DOMAIN` — публичное имя стенда для `server_name` nginx и сертификата
     (`project-documents-max.ru`, уже стоит в `.env.example`);
   - `PUBLIC_BASE_URL` — `https://<DOMAIN>`, нужен боту в режиме webhook;
   - `BOT_WEBHOOK_SECRET` — 16+ символов, MAX присылает его в заголовке вебхука.
     Остальное имеет дефолты (`ENV=production` и `BOT_MODE=webhook` compose выставляет
     сам). Плейсхолдеры `dev-only-*` из `.env.example` в production отвергаются на старте.
     Полезно задать `MAX_MINI_APP_NAME` (кнопка «Открыть» под сообщениями бота),
     `ADMIN_MAX_IDS`, `GIGACHAT_AUTH_KEY` и `ACME_EMAIL` (почта учётки Let's Encrypt).
3. `./deploy.sh` — проверит `DOMAIN`, создаст каталоги `app_logs/{api,bot,nginx}`,
   `backups/` и `gateway/letsencrypt/` с владельцами под uid контейнеров, соберёт
   образы, прогонит тесты в образе, выпустит сертификат (ниже), поднимет стек и
   дождётся healthcheck'ов; миграции api применит сам при старте (advisory-lock
   защищает от гонки воркеров).
4. Проверка: `./maxapp --prod health`, `./maxapp --prod logs bot`,
   `curl -I https://project-documents-max.ru` (200, сертификат Let's Encrypt). Бот
   при старте в режиме webhook сам регистрирует подписку в MAX на
   `PUBLIC_BASE_URL + BOT_WEBHOOK_PATH`; мини-апп открывается из чата с ботом.

## Сертификат

Выпуском и продлением занимается контейнер `certbot` (`gateway/certbot.sh`),
руками ничего делать не нужно:

- При первом запуске `deploy.sh` кладёт в `gateway/ssl/` самоподписанную пару
  (без неё nginx не стартует), поднимает `gateway` и `certbot` и ждёт до двух
  минут, пока Let's Encrypt проверит домен по http-01 через общий webroot
  `gateway/acme/`. Бот стартует уже с настоящим сертификатом.
- Выпущенная пара копируется в `gateway/ssl/`; `gateway` замечает замену и
  перечитывает конфиг сам (`gateway/cert-reload.sh`, проверка раз в минуту).
- Продление certbot проверяет дважды в сутки; учётка и история выпусков — в
  `gateway/letsencrypt/` (в git не попадает).
- Не выпустился (DNS ещё не обновился, закрыт порт 80) — `deploy.sh` так и скажет,
  а certbot повторяет попытку каждые 15 минут: `./maxapp --prod logs certbot`.
  После выпуска перезапустите бота, чтобы он заново зарегистрировал вебхук:
  `docker compose -f docker-compose.prod.yml restart bot`.

Свой сертификат (например, от регистратора) — положить `fullchain.pem` и
`privkey.pem` в `gateway/ssl/` и не поднимать `certbot`
(`docker compose -f docker-compose.prod.yml stop certbot`).

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
| `certbot`   | certbot/certbot      | выпуск и продление сертификата Let's Encrypt для `DOMAIN` в `gateway/ssl/`      |
| `db_backup` | postgres:17-alpine   | суточный `pg_dump` в `backups/` в `DB_BACKUP_HOUR_UTC`, хранит `DB_BACKUP_KEEP` |

`api`, `bot` и `certbot` работают с read-only FS, `tmpfs /tmp`, `cap_drop ALL`,
`no-new-privileges` и лимитами памяти и pids; `db`, `redis`, `gateway` и `certbot` —
с точечными `cap_add` под свои entrypoint'ы и `no-new-privileges`; `db_backup`
получает только переменные дампа.
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

## Домашний компьютер вместо сервера

Тот же прод-стенд поднимается и на своей машине, если у подключения белый
(статический) IP: A-запись домена — на этот IP, на роутере проброс внешних
портов 80 и 443 на компьютер, затем `docker compose down` (dev и прод используют
одни имена контейнеров) и `./deploy.sh` (Linux, от root: он выставляет владельцев
каталогов). Мини-апп и бот работают, пока компьютер включён; для проверки жюри и
постоянной работы нужен сервер.

Туннели на чужих доменах (cloudflared, ngrok) подходят только для отладки dev-стенда:
URL мини-аппа в MAX тогда придётся менять на адрес туннеля, а домен
`project-documents-max.ru` останется без стенда.

## Один бот на прод и локальный стенд

Бот в dev работает polling'ом, а SDK при запуске polling'а снимает все
вебхук-подписки бота — локальный `docker compose up` с тем же `MAX_BOT_TOKEN`
молча отключил бы прод. Поэтому бот в polling-режиме сначала смотрит подписки и,
если вебхук уже есть, polling не запускает: в логе `bot.polling.blocked` с адресом
вебхука, а файлы документов локальный стенд в чат по-прежнему доставляет. Для
отладки входящих сообщений заведите в MasterBot второго бота и укажите его токен в
локальном `.env`; забрать апдейты у прода насовсем — `BOT_POLLING_TAKEOVER=true`
(прод-бот подпишется снова только при своём рестарте).

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
