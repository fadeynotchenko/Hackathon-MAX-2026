# Платформа MAX: что использует проект

Источник — документация разработчиков MAX (https://dev.max.ru) и типы официального
SDK `@maxhub/max-bot-api`. Здесь только то, на что опирается код.

## Bot API

- Хост `https://platform-api2.max.ru`, токен в заголовке `Authorization: <token>`
  (query-параметр больше не поддерживается). SDK делает это сам.
- Получение апдейтов: long polling `GET /updates` (dev) или webhook `POST /subscriptions`
  (прод). Бот выбирает режим по `BOT_MODE`; в webhook-режиме SDK сам регистрирует
  подписку на `PUBLIC_BASE_URL + BOT_WEBHOOK_PATH` и проверяет заголовок
  `x-max-bot-api-secret` (`BOT_WEBHOOK_SECRET`) сравнением за константное время.
- Апдейты, на которые подписан бот: `bot_started` (пользователь нажал «Начать»,
  есть `payload` из deep-link), `message_created`, `message_callback` (нажатие
  inline-кнопки, отвечаем `answerOnCallback`).
- Отправка: `sendMessageToUser(userId, text, { format: 'markdown' | 'html', attachments })`.
  Уведомления из core доставляет именно бот (событие `notify.user`), у core нет
  прямого клиента Bot API.
- Inline-клавиатура: до 30 рядов; типы кнопок `callback`, `link`, `open_app`
  (`web_app` — имя мини-аппа, пусто = мини-апп бота), `request_contact`,
  `request_geo_location`, `message`, `clipboard`. Сборка — `Keyboard.inlineKeyboard`
  в `bot/src/keyboards/main.ts`.

## TLS: корень Минцифры

`platform-api2.max.ru` подписан цепочкой «Russian Trusted Sub CA → Russian Trusted
Root CA». Этого корня нет в хранилищах Node, Debian и macOS, поэтому без него бот
падает с `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` на первом же запросе. Корень лежит в
`bot/certs/russian_trusted_root_ca.pem`, образ бота и dev-compose подключают его через
`NODE_EXTRA_CA_CERTS` (подробности и отпечаток — `bot/certs/README.md`).

## Мини-приложение

- Мост: `<script src="https://st.max.ru/js/max-web-app.js">` создаёт `window.WebApp`.
  Обёртка с типами — `web/src/max/webapp.ts`; CSP gateway разрешает этот источник в
  `script-src` и `connect-src`.
- `WebApp.initData` — подписанная строка `key=value&…` с `query_id`, `user` (JSON:
  `id`, `first_name`, `last_name`, `username`, `language_code`, `photo_url`),
  `auth_date`, `start_param` (из `?startapp=`), `chat`, `hash`. Клиент отправляет её
  как есть в `POST /api/v1/auth/max`; разбирать `initDataUnsafe` на клиенте для
  идентификации нельзя.
- Проверка на сервере (`core.domain.initdata`): пары без `hash` сортируются по ключу
  и склеиваются `\n`; `secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)`;
  `hash == hex(HMAC_SHA256(secret_key, data_check_string))`; `auth_date` не старше
  `INIT_DATA_MAX_AGE_SECONDS` (по умолчанию час: утёкшая строка initData даёт вход
  всё это время, а клиент MAX выдаёт свежую при каждом запуске). Тот же токен, что у бота.
- Тема: `WebApp.themeParams` и `colorScheme` → CSS-переменные `--max-*`
  (`applyTheme`). Кнопки и отклик: `BackButton`, `HapticFeedback`; `ready()` и
  `expand()` вызываются после успешного входа.
- Веб-клиент MAX открывает мини-апп во фрейме: `frame-ancestors` в CSP разрешает
  `max.ru` и поддомены, `X-Frame-Options` не ставится.
- Ссылки: бот `https://max.ru/<username>`, запуск мини-аппа с параметром
  `https://max.ru/<username>?startapp=<value>`; значение приходит в
  `initData.start_param`.

## Локальная разработка без клиента MAX

`cd core && uv run python -m core.scripts.dev_init_data` печатает подписанный initData для
`VITE_DEV_INIT_DATA`: мини-апп в обычном браузере проходит настоящий вход, без
заглушек в коде авторизации. Бот в dev работает polling'ом и не требует
публичного адреса.
