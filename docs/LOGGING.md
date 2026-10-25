# Логирование

Ядро (`core.logs`) и бот (pino) пишут JSON с одинаковыми полями, поэтому
агрегатор и `grep` работают одинаково поверх `app_logs/*.log` и
`docker compose logs`

## Схема записи

```json
{
  "ts": "2026-09-16T10:00:00.123Z",
  "level": "info",
  "service": "api",
  "logger": "core.usecases.auth.login",
  "event": "auth.login.ok",
  "msg": "auth.login.ok",
  "request_id": "3f2c…",
  "user_id": 42,
  "max_user_id": 1001
}
```

| Поле         | Значение                                                                                               |
| ------------ | ------------------------------------------------------------------------------------------------------ |
| `ts`         | ISO-8601 UTC                                                                                           |
| `level`      | `debug`, `info`, `warning`, `error`; pino переименовывает `warn` в `warning`, `LOG_LEVEL` понимает оба |
| `service`    | `api`, `bot` или имя джобы                                                                             |
| `event`      | `<домен>.<действие>`: `auth.login.ok`, `events.published`, `http.request`, `bot.update`                |
| `msg`        | текст, для событий совпадает с `event`                                                                 |
| `request_id` | из `X-Request-ID` (ставит nginx) или сгенерированный, у джоб id прогона                                |
| `user_id`    | внутренний id пользователя, если известен                                                              |
| `err`        | `{type, message, stack}` при исключении                                                                |
| прочее       | поля события: `duration_ms`, `status`, `event_id` и другие                                             |

## Куда пишется

| Куда                    | Формат и ротация                                                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| stdout контейнера       | JSON (`LOG_FORMAT=json`, прод) или цветная строка (`pretty`, dev); `docker compose logs` ротируется по объёму (`x-logging`) |
| `LOG_DIR/<service>.log` | всегда JSON, ротация раз в сутки по UTC: `api.<дата>.log.gz` (Python), `bot.<дата>.N.log` (pino-roll)                       |
| gateway                 | `app_logs/nginx/access-<дата>.log`, формат `maxapp_evidence` с полем `rid=$request_id`                                      |

`LOG_DIR=` (явно пусто) выключает файл и в ядре, и в боте. Хранение бессрочное,
чистит человек. В проде у каждого сервиса свой подкаталог `app_logs/<сервис>` с
владельцем под uid контейнера

## Что в лог не попадает

- секреты, токены и сырая строка initData
- значения полей документов: помощник пишет, какие поля он записал, отклонил или
  отбросил, но без самих значений
- содержимое присланных фото, сканов и голосовых

## Как писать в коде

Python:

```python
from core.logs import biz_info, biz_warn, biz_error

biz_info(logger, "auth.login.ok", user_id=user.id, max_user_id=max_user.id)
biz_error(logger, "events.worker.crashed", error=str(exc), exc_info=exc)
```

Бот:

```ts
log.info({ event: 'bot.update', update_type: ctx.updateType, user_id }, 'update handled');
log.error({ event: 'events.handler.failed', event_id: event.id, err }, 'handler failed');
```

Правила: имя события постоянная строка `<домен>.<действие>`, поля передаются
аргументами, а не вклеиваются в текст. `request_id` и `user_id` в Python
подмешиваются из contextvars сами

## Разбор инцидента

1. Пользователь присылает `request_id` из ответа API: поле есть в каждой ошибке
2. `grep <request_id> app_logs/api/api.log app_logs/nginx/access-*.log` находит строку
   gateway (IP, статус, время) и строки ядра (кто, что делал, где упало)
3. Для событий бота `event_id` из ответа `/send` или `/admin/notify` совпадает с
   `event_id` в `events.published` (ядро) и в `events.handled` (бот)
