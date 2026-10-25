# Платформа MAX: что использует проект

Источник: документация разработчиков MAX (https://dev.max.ru) и типы официального
SDK `@maxhub/max-bot-api`. Здесь только то, на что опирается код

## Bot API

**Хост и авторизация.** `https://platform-api2.max.ru`, токен в заголовке
`Authorization: <token>` (query-параметр больше не поддерживается). SDK делает это
сам

**Получение апдейтов.** Long polling `GET /updates` в dev или webhook
`POST /subscriptions` в проде, режим выбирает `BOT_MODE`. В режиме webhook SDK сам
регистрирует подписку на `PUBLIC_BASE_URL + BOT_WEBHOOK_PATH` и сверяет заголовок
`x-max-bot-api-secret` с `BOT_WEBHOOK_SECRET` за константное время. Запуск
polling'а в SDK снимает все подписки бота, поэтому бот сначала читает
`GET /subscriptions` и при живом вебхуке polling не запускает
(`bot/src/webhook-guard.ts`, обход `BOT_POLLING_TAKEOVER=true`)

**Апдейты, на которые подписан бот:**

| Апдейт             | Когда приходит                                           |
| ------------------ | -------------------------------------------------------- |
| `bot_started`      | пользователь нажал «Начать», есть `payload` из deep-link |
| `message_created`  | сообщение, фото, файл или голосовое                      |
| `message_callback` | нажатие inline-кнопки, бот отвечает `answerOnCallback`   |

**Отправка.** `sendMessageToUser(userId, text, { format: 'markdown' | 'html', attachments })`.
Уведомления из ядра доставляет именно бот (событие `notify.user`), прямого клиента
Bot API у ядра нет

**Разметка.** Приветствие, помощь и ответы помощника уходят с `format: 'html'`
(`<b>`, `<i>`, `<code>`). Всё, что пришло от человека или модели, экранируется
(`fmt.escapeHtml` в боте, `html.escape` в ядре). Слишком длинный ответ ядро
обрезает и шлёт простым текстом: HTML, обрезанный посреди тега, MAX не примет. В
апдейте нажатия кнопки текст приходит без HTML (разметка идёт отдельным списком
`markup`), поэтому бот хранит HTML сообщений с кнопками в Redis
(`messages:markup:<mid>`, неделя). После нажатия кнопки снимаются, жирный шрифт
остаётся

**Inline-клавиатура.** До 30 рядов, типы кнопок `callback`, `link`, `open_app`,
`request_contact`, `request_geo_location`, `message`, `clipboard`. Сборка в
`bot/src/keyboards/main.ts` через `Keyboard.inlineKeyboard`

У `open_app` поле `web_app` (имя мини-аппа) обязательно: без него API отвечает
`400 Field 'webApp' cannot be null` и не доставляет сообщение целиком. Поэтому
`mainKeyboard` без `MAX_MINI_APP_NAME` кнопку не рисует. У нашего бота имя
мини-аппа совпадает с username: `t409_hakaton_max_bot`. `payload` кнопки приходит в
`initData.start_param`, и мини-апп открывается сразу на нужном экране (`create`,
`archive`, `doc_<id>`, см. `web/src/lib/startRoute.ts`). Кнопка под готовым файлом
ведёт на карточку документа

## TLS: корень Минцифры

`platform-api2.max.ru` подписан цепочкой «Russian Trusted Sub CA», «Russian Trusted
Root CA». Этого корня нет в хранилищах Node, Debian и macOS, и без него бот падает
с `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` на первом же запросе. Корень лежит в
`bot/certs/russian_trusted_root_ca.pem`, образ бота и dev-compose подключают его
через `NODE_EXTRA_CA_CERTS`. Отпечаток и источник в
[bot/certs/README.md](../bot/certs/README.md)

## Мини-приложение

**Мост.** `<script src="https://st.max.ru/js/max-web-app.js">` создаёт
`window.WebApp`. Обёртка с типами в `web/src/max/webapp.ts`, CSP gateway разрешает
этот источник в `script-src` и `connect-src`

**initData.** Подписанная строка `key=value&…` с полями `query_id`, `user` (JSON:
`id`, `first_name`, `last_name`, `username`, `language_code`, `photo_url`),
`auth_date`, `start_param` (из `?startapp=`), `chat`, `hash`. Клиент отправляет её
как есть в `POST /api/v1/auth/max`. Разбирать `initDataUnsafe` на клиенте для
идентификации нельзя

**Проверка подписи на сервере** (`core.domain.initdata`):

1. пары без `hash` сортируются по ключу и склеиваются через `\n`
2. ключ: `secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)`
3. сверка: `hash == hex(HMAC_SHA256(secret_key, data_check_string))`
4. `auth_date` не старше `INIT_DATA_MAX_AGE_SECONDS` (по умолчанию час: клиент MAX
   выдаёт свежую строку при каждом запуске)

**Интерфейс.** Дизайн-система MAX, пакет `@maxhub/max-ui` (https://dev.max.ru/ui).
Провайдер `<MaxUI>` получает `colorScheme` и `platform` из моста
(`WebApp.colorScheme`, `WebApp.platform`, событие `themeChanged`), вне MAX берёт
системную тему. Стили приложения используют только токены MAX UI
(`--background-*`, `--text-*`, `--spacing-*`), своих цветов нет

**Кнопки и отклик.** Системная `BackButton` (вне MAX та же кнопка рисуется в
шапке), `HapticFeedback`, при старте `ready()` и `expand()`. `close()` не
используется: мини-апп закрывается системной кнопкой клиента

**Фрейм.** Веб-клиент MAX открывает мини-апп во фрейме: `frame-ancestors` в CSP
разрешает `max.ru` и поддомены, `X-Frame-Options` не ставится

**Ссылки.** Бот `https://max.ru/<username>`, запуск мини-аппа с параметром
`https://max.ru/<username>?startapp=<value>`, значение приходит в
`initData.start_param`

## Локальная разработка без клиента MAX

`cd core && uv run python -m core.scripts.dev_init_data` печатает подписанный
initData для `VITE_DEV_INIT_DATA`: мини-апп в обычном браузере проходит настоящий
вход, без заглушек в коде авторизации. На dev-стенде то же делает ручка
`GET /api/v1/dev/init-data` (только при `DEV_LOGIN_ENABLED` и вне production). Бот
в dev работает polling'ом и не требует публичного адреса
