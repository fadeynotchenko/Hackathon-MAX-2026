# TLS-материалы

Сюда на сервере кладутся `fullchain.pem` и `privkey.pem` (Let's Encrypt через
certbot или сертификат от регистратора). Каталог монтируется в контейнер nginx
только на чтение; содержимое в git не попадает (`.gitignore`).

Первый запуск: если файлов нет, `deploy.sh` кладёт самоподписанную пару на 30 дней,
чтобы gateway поднялся и отдавал `/.well-known/acme-challenge/` из `gateway/acme`.
После этого выпуск настоящего сертификата:

```bash
certbot certonly --webroot -w ./gateway/acme -d "$DOMAIN"
cp /etc/letsencrypt/live/$DOMAIN/{fullchain,privkey}.pem ./gateway/ssl/
docker compose -f docker-compose.prod.yml exec gateway nginx -s reload
```

Продление (таймер certbot ставит сам): подключить копирование и перезагрузку хуком,
иначе через 90 дней nginx продолжит отдавать протухший файл:

```bash
certbot renew --deploy-hook "cp /etc/letsencrypt/live/$DOMAIN/{fullchain,privkey}.pem /opt/maxapp/gateway/ssl/ && docker compose -f /opt/maxapp/docker-compose.prod.yml exec gateway nginx -s reload"
```

HSTS в `security_headers.conf` объявлен с `includeSubDomains`: все поддомены
`DOMAIN` обязаны отвечать по https.
