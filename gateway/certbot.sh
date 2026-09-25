#!/bin/sh
# Сертификат Let's Encrypt для gateway: выпуск, если его ещё нет, и продление.
# Работает в контейнере certbot (docker-compose.prod.yml), который стартует
# после healthy gateway: проверка владения доменом (http-01) идёт через общий
# webroot /var/www/acme, а его gateway отдаёт на :80.
#
# Готовая пара копируется в /etc/nginx/ssl (на хосте gateway/ssl) под именами,
# которые читает nginx; gateway замечает замену и перечитывает конфиг сам
# (gateway/cert-reload.sh). Учётка и история выпусков — в gateway/letsencrypt.
set -u
umask 077

WEBROOT=/var/www/acme
SSL_DIR=/etc/nginx/ssl
LIVE="/etc/letsencrypt/live/${DOMAIN:-}"
# Let's Encrypt пускает не больше пяти неудачных проверок домена в час.
RETRY_SECONDS=900
RENEW_SECONDS=43200

log() { echo "[certbot] $*"; }

idle() {
  while :; do sleep 86400; done
}

case "${DOMAIN:-}" in
  '' | *.example.tld | localhost)
    log "DOMAIN не задан в .env, выпускать сертификат не для чего"
    idle
    ;;
esac

install_pair() {
  # Через временный файл и mv: gateway не должен прочитать половину файла.
  for name in privkey fullchain; do
    if ! cmp -s "$LIVE/$name.pem" "$SSL_DIR/$name.pem"; then
      cp "$LIVE/$name.pem" "$SSL_DIR/.$name.pem.new" &&
        mv -f "$SSL_DIR/.$name.pem.new" "$SSL_DIR/$name.pem" &&
        log "$name.pem обновлён в gateway/ssl"
    fi
  done
}

until [ -f "$LIVE/fullchain.pem" ]; do
  log "выпуск сертификата для $DOMAIN"
  set -- --webroot -w "$WEBROOT" -d "$DOMAIN" --cert-name "$DOMAIN" --non-interactive --agree-tos
  if [ -n "${ACME_EMAIL:-}" ]; then
    set -- "$@" --email "$ACME_EMAIL" --no-eff-email
  fi
  if certbot certonly "$@"; then
    break
  fi
  log "не выпущен: A-запись $DOMAIN должна вести на этот сервер, порт 80 — быть открыт снаружи; повтор через $((RETRY_SECONDS / 60)) мин"
  sleep "$RETRY_SECONDS"
done

while :; do
  install_pair
  sleep "$RENEW_SECONDS"
  # Продлевает только то, чему пора (certbot сам сверяется со сроком и ARI).
  certbot renew --non-interactive --quiet || log "продление не удалось, повтор через 12 ч"
done
