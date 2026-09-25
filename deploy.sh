#!/usr/bin/env bash
# Деплой на прод-хост. Запускать из корня репозитория на сервере:
#
#   ./deploy.sh              # полный цикл
#   SKIP_TESTS=1 ./deploy.sh # без прогона тестов (только если они уже зелёные в CI)
#
# Шаги:
#   1. проверки: .env на месте и с настоящим DOMAIN, docker и git доступны;
#   2. git pull --ff-only;
#   3. тесты core внутри тестового образа (core/Dockerfile, target test) — красные = нет деплоя;
#   4. каталоги логов/бэкапов с правами под uid контейнеров, самоподписанный TLS при первом запуске;
#   5. первый выпуск Let's Encrypt (gateway + certbot) до старта бота;
#   6. снимок БД перед выкаткой (best-effort, ротация PREDEPLOY_KEEP);
#   7. docker compose up -d --build --remove-orphans --wait (api применит миграции при старте);
#   8. сводка контейнеров, health API и сертификата, чистка старых слоёв.
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

# Значение из .env так, как его увидит compose: последняя строка, без кавычек.
env_value() { sed -n "s/^$1=//p" .env | tail -n 1 | tr -d "\"'"; }
DOMAIN="$(env_value DOMAIN)"
case "$DOMAIN" in
  '' | *.example.tld) fail "DOMAIN в .env не задан: нужен адрес мини-аппа, например DOMAIN=project-documents-max.ru" ;;
esac
if [ "$(env_value PUBLIC_BASE_URL)" != "https://$DOMAIN" ]; then
  log "WARNING: PUBLIC_BASE_URL в .env не https://$DOMAIN — бот зарегистрирует вебхук не на этот стенд"
fi

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
# Каталог с числовым владельцем: у uid контейнеров на хосте нет имён, а
# `install -o 10001` из uutils coreutils (Ubuntu 26.04) числовой uid не принимает.
owned_dir() { mkdir -p "$3" && chown "$2:$2" "$3" && chmod "$1" "$3"; }
# Bind-mount создаётся Docker'ом как root:root, а api (uid 10001), бот (uid 1000)
# и воркер nginx (uid 101) пишут в него непривилегированно. Без этого api падает
# на первой же записи в файл лога.
owned_dir 0750 10001 ./app_logs/api
# Файлы документов пишет тот же uid, что и логи api; 0750 — чужие в них не ходят.
owned_dir 0750 10001 ./app_data/api
owned_dir 0750 1000 ./app_logs/bot
owned_dir 0750 101 ./app_logs/nginx
install -d -m 0700 ./backups

log "TLS: сертификат gateway"
# Учётка Let's Encrypt и история выпусков контейнера certbot.
install -d -m 0700 ./gateway/letsencrypt
if [ ! -f ./gateway/ssl/fullchain.pem ] || [ ! -f ./gateway/ssl/privkey.pem ]; then
  # Без пары сертификатов nginx не стартует, а certbot по webroot нужен работающий
  # nginx: замкнутый круг. Самоподписанная пара поднимает gateway для первого
  # выпуска через ACME, потом контейнер certbot заменяет её настоящей.
  install -d -m 0700 ./gateway/ssl
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=$DOMAIN" \
    -keyout ./gateway/ssl/privkey.pem -out ./gateway/ssl/fullchain.pem >/dev/null 2>&1
  log "поставлена самоподписанная пара на 30 дней, настоящую выпустит контейнер certbot"
fi

# Заглушка первого запуска подписана сама собой: издатель совпадает с субъектом.
cert_is_self_signed() {
  local pem=./gateway/ssl/fullchain.pem
  [ "$(openssl x509 -in "$pem" -noout -issuer | sed 's/^issuer=//')" = \
    "$(openssl x509 -in "$pem" -noout -subject | sed 's/^subject=//')" ]
}

if cert_is_self_signed; then
  # Бот при старте регистрирует вебхук в MAX на https://$DOMAIN, а мини-апп в
  # клиенте MAX не откроется с самоподписанным сертификатом. Поэтому сначала
  # gateway и certbot (gateway тянет за собой api, db и redis), бот — после.
  log "первый выпуск Let's Encrypt для $DOMAIN (до 2 минут)"
  $COMPOSE up -d --build gateway certbot
  for _ in $(seq 1 24); do
    cert_is_self_signed || break
    sleep 5
  done
  if cert_is_self_signed; then
    log "WARNING: сертификат не выпущен. Проверьте, что A-запись $DOMAIN ведёт на этот сервер, а порты 80 и 443 открыты снаружи."
    log "WARNING: certbot повторяет попытку каждые 15 минут (./maxapp --prod logs certbot); после выпуска перезапустите бота: $COMPOSE restart bot"
  else
    # gateway и сам перечитает пару в течение минуты, но бот стартует прямо сейчас.
    $COMPOSE exec -T gateway nginx -s reload || log "WARNING: gateway не перечитал конфиг, подхватит пару сам в течение минуты"
    log "сертификат Let's Encrypt получен"
  fi
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
if cert_is_self_signed; then
  log "WARNING: https://$DOMAIN пока с самоподписанным сертификатом, мини-апп в MAX не откроется: ./maxapp --prod logs certbot"
else
  log "TLS: $(openssl x509 -in ./gateway/ssl/fullchain.pem -noout -issuer), до $(openssl x509 -in ./gateway/ssl/fullchain.pem -noout -enddate | cut -d= -f2)"
fi
# Старые слои образов после пересборки не нужны.
docker image prune -f >/dev/null 2>&1 || true
log "готово"
