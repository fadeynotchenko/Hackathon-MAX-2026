#!/bin/sh
# nginx читает сертификат только при старте и reload, а пару в /etc/nginx/ssl
# меняет контейнер certbot (выпуск и продление, gateway/certbot.sh). Фоновый
# цикл замечает замену и перечитывает конфиг: certbot не нужен docker.sock,
# а после выпуска не нужен ручной `nginx -s reload`.
#
# Официальный образ nginx запускает скрипты /docker-entrypoint.d/ перед стартом;
# цикл уходит в фон и живёт рядом с master-процессом.
SSL_DIR=/etc/nginx/ssl

stamp() {
  stat -c '%i %Y %s' "$SSL_DIR/fullchain.pem" "$SSL_DIR/privkey.pem" 2>/dev/null | tr '\n' ' '
}

(
  last=$(stamp)
  while sleep 60; do
    current=$(stamp)
    [ "$current" = "$last" ] && continue
    # Пара меняется двумя файлами: даём certbot дописать второй.
    sleep 5
    last=$(stamp)
    if nginx -t -q; then
      nginx -s reload && echo "[gateway] сертификат сменился, nginx перечитал конфиг"
    else
      echo "[gateway] новый сертификат не прошёл nginx -t, работает прежний"
    fi
  done
) </dev/null &
