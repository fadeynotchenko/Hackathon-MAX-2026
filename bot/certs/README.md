# Корневые сертификаты, которых нет в стандартных хранилищах

`russian_trusted_root_ca.pem` — «Russian Trusted Root CA» Минцифры. Под ним
выпущен сертификат `*.max.ru`, включая хост Bot API `platform-api2.max.ru`.
В хранилищах Node, Debian и macOS этого корня нет, поэтому без него бот получает
`UNABLE_TO_GET_ISSUER_CERT_LOCALLY` и не может ни принять апдейт, ни отправить
сообщение.

Как используется:

- `bot/Dockerfile` копирует файл в образ и выставляет `NODE_EXTRA_CA_CERTS`;
- dev-compose передаёт тот же путь контейнеру бота;
- локальный запуск без Docker: скрипт `dev` в `bot/package.json` подставляет
  `NODE_EXTRA_CA_CERTS=./certs/russian_trusted_root_ca.pem`.

Источник: https://www.gosuslugi.ru/crt (файл `russian_trusted_root_ca_pem.crt`).
Отпечаток SHA-256 после скачивания сверить с опубликованным:

```
D2:6D:2D:02:31:B7:C3:9F:92:CC:73:85:12:BA:54:10:35:19:E4:40:5D:68:B5:BD:70:3E:97:88:CA:8E:CF:31
```

Срок действия корня — до 2032-02-27.
