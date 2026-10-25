# TLS-материалы

На сервере здесь лежат `fullchain.pem` и `privkey.pem`, которые читает nginx.
Каталог монтируется в gateway только на чтение, содержимое в git не попадает
(`.gitignore`). Руками сюда ничего класть не нужно

## Жизненный цикл

| Этап          | Кто и как                                                                                                       |
| ------------- | --------------------------------------------------------------------------------------------------------------- |
| первый запуск | `deploy.sh` ставит самоподписанную пару на 30 дней: без неё nginx не стартует и Let's Encrypt не проверит домен |
| выпуск        | контейнер `certbot` (`gateway/certbot.sh`) по http-01 через webroot `gateway/acme/`, пара копируется сюда       |
| продление     | certbot проверяет дважды в сутки, учётка Let's Encrypt в `gateway/letsencrypt/`                                 |
| подхват       | gateway раз в минуту сверяет файлы и после замены делает `nginx -s reload` (`gateway/cert-reload.sh`)           |

Статус выпуска: `./maxapp --prod logs certbot`. Выпуск заново с нуля: удалить
`gateway/letsencrypt/` и перезапустить контейнер
`docker compose -f docker-compose.prod.yml restart certbot`

Свой сертификат (от регистратора) кладётся сюда под теми же именами, `certbot`
тогда останавливается: `docker compose -f docker-compose.prod.yml stop certbot`

HSTS в `gateway/snippets/security_headers.conf` объявлен с `includeSubDomains`:
все поддомены `DOMAIN` обязаны отвечать по https
