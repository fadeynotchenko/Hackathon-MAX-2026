#!/usr/bin/env bash
# Деплой на прод-хост. Запускать из корня репозитория на сервере:
#
#   ./deploy.sh              # полный цикл
#   SKIP_TESTS=1 ./deploy.sh # без прогона тестов (только если они уже зелёные в CI)
#
# Шаги:
#   1. проверки: .env на месте, docker и git доступны;
#   2. git pull --ff-only;
#   3. тесты core внутри тестового образа (core/Dockerfile, target test) — красные = нет деплоя;
#   4. каталоги логов/бэкапов с правами под uid контейнеров, самоподписанный TLS при первом запуске;
#   5. снимок БД перед выкаткой (best-effort, ротация PREDEPLOY_KEEP);
#   6. docker compose up -d --build --remove-orphans --wait (api применит миграции при старте);
#   7. сводка контейнеров и health API, чистка старых слоёв.
#
# Правки .env делаются ДО запуска: контейнеры перечитают его при пересоздании.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
COMPOSE="docker compose -f docker-compose.prod.yml"

log() { printf '[deploy] %s\n' "$*"; }
fail() { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

log "cwd: $PWD"
[ -f .env ] || fail ".env не найден рядом с docker-compose.prod.yml"
command -v git >/dev/null || fail "git не найден"
command -v docker >/dev/null || fail "docker не найден"

log "git pull --ff-only"
git pull --ff-only

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  log "сборка тестового образа core и прогон pytest"
  docker build --target test -t maxapp-core-test:latest core >/dev/null
  # Замки tests/repo читают файлы репозитория (compose, gateway, docs): монтируем его
  # read-only. PYTHONPATH ставит пакет core из монтирования впереди копии в образе,
  # чтобы скрипты вычисляли корень репозитория как /repo; кеш линтера отключён —
  # писать в read-only каталог нельзя.
  if ! docker run --rm -e LOG_DIR= -e PYTHONPATH=/repo/core/src \
       -v "$ROOT_DIR:/repo:ro" -w /repo/core maxapp-core-test:latest \
       python -m pytest tests -q --tb=short -p no:cacheprovider; then
    docker rmi maxapp-core-test:latest >/dev/null 2>&1 || true
    fail "тесты красные, деплой остановлен"
  fi
  docker rmi maxapp-core-test:latest >/dev/null 2>&1 || true
  log "тесты зелёные"
fi

log "каталоги логов и бэкапов с владельцами контейнеров"
# Bind-mount создаётся Docker'ом как root:root, а api (uid 10001), бот (uid 1000)
# и воркер nginx (uid 101) пишут в него непривилегированно. Без этого api падает
# на первой же записи в файл лога.
install -d -m 0750 -o 10001 -g 10001 ./app_logs/api
install -d -m 0750 -o 1000 -g 1000 ./app_logs/bot
install -d -m 0750 -o 101 -g 101 ./app_logs/nginx
install -d -m 0700 ./backups

log "TLS: сертификат gateway"
if [ ! -f ./gateway/ssl/fullchain.pem ] || [ ! -f ./gateway/ssl/privkey.pem ]; then
  # Без пары сертификатов nginx не стартует, а certbot по webroot нужен работающий
  # nginx: замкнутый круг. Самоподписанная пара поднимает gateway для первого
  # выпуска через ACME (см. gateway/ssl/README.md), потом её заменяет настоящая.
  install -d -m 0700 ./gateway/ssl
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
    -subj "/CN=$(grep -E '^DOMAIN=' .env | cut -d= -f2- | tr -d '\"')" \
    -keyout ./gateway/ssl/privkey.pem -out ./gateway/ssl/fullchain.pem >/dev/null 2>&1
  log "WARNING: поставлен самоподписанный сертификат на 30 дней, выпустите настоящий (gateway/ssl/README.md)"
fi

log "снимок БД перед выкаткой (best-effort)"
if $COMPOSE ps db --status running 2>/dev/null | grep -q maxapp_db; then
  # Дамп — вся база; читать его должен только владелец.
  umask 077
  SNAP="./backups/predeploy_$(date +%Y%m%d_%H%M%S).dump"
  if $COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$SNAP" 2>/dev/null; then
    log "снимок: $SNAP"
    # Ротация своя, отдельно от суточных дампов db_backup: серия выкаток за день
    # не должна вытеснять суточную историю.
    ls -1t ./backups/predeploy_*.dump 2>/dev/null | tail -n +"$(( ${PREDEPLOY_KEEP:-10} + 1 ))" \
      | while read -r old; do rm -f "$old"; done || true
  else
    rm -f "$SNAP"
    log "WARNING: снимок не удался, продолжаем"
  fi
else
  log "контейнер db не запущен, снимок пропущен (первый деплой)"
fi

log "docker compose up -d --build --remove-orphans --wait"
# --wait ждёт healthcheck'и (api до 20 с стартует и мигрирует): ложных предупреждений нет.
$COMPOSE up -d --build --remove-orphans --wait --wait-timeout 180

log "контейнеры:"
$COMPOSE ps
log "health API:"
$COMPOSE exec -T api curl -fsS http://127.0.0.1:8000/api/v1/health && echo || log "WARNING: API не отвечает, проверьте ./maxapp --prod logs api"
# Старые слои образов после пересборки не нужны.
docker image prune -f >/dev/null 2>&1 || true
log "готово"
