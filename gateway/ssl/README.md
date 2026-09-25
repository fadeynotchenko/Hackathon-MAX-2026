# TLS-материалы

Здесь на сервере лежат `fullchain.pem` и `privkey.pem`, которые читает nginx.
Каталог монтируется в gateway только на чтение, содержимое в git не попадает
(`.gitignore`). Руками сюда ничего класть не нужно:

- первый запуск `deploy.sh` ставит самоподписанную пару на 30 дней — без неё nginx
  не стартует, а без работающего nginx Let's Encrypt не проверит домен;
- контейнер `certbot` (`gateway/certbot.sh`) выпускает сертификат для `DOMAIN` по
  http-01 через webroot `gateway/acme/`, копирует пару сюда и дважды в сутки
  проверяет продление; учётка Let's Encrypt — в `gateway/letsencrypt/`;
- gateway раз в минуту сверяет файлы и после замены делает `nginx -s reload`
  (`gateway/cert-reload.sh`).

Статус выпуска: `./maxapp --prod logs certbot`. Выпуск заново с нуля — удалить
`gateway/letsencrypt/` и перезапустить контейнер:
`docker compose -f docker-compose.prod.yml restart certbot`.

Свой сертификат (от регистратора) кладётся сюда под теми же именами, `certbot`
тогда не поднимается: `docker compose -f docker-compose.prod.yml stop certbot`.

HSTS в `security_headers.conf` объявлен с `includeSubDomains`: все поддомены
`DOMAIN` обязаны отвечать по https.
