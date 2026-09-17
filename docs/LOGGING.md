# Логирование

Один формат для всех сервисов: core (`core.logs`) и бот (pino) пишут JSON
с одинаковыми полями, поэтому агрегатор и `grep` работают одинаково поверх
`app_logs/*.log` и `docker compose logs`.

## Схема записи

```json
{
  "ts": "2026-09-16T10:00:00.123Z",
  "level": "info",
  "service": "api",
  "logger": "services.auth.login",
  "event": "auth.login.ok",
  "msg": "auth.login.ok",
  "request_id": "3f2c…",
  "user_id": 42,
  "max_user_id": 1001
}
```

| Поле         | Значение                                                                                                            |
| ------------ | ------------------------------------------------------------------------------------------------------------------- |
| `ts`         | ISO-8601 UTC                                                                                                        |
| `level`      | `debug` / `info` / `warning` / `error` (pino переименовывает `warn` → `warning`; `LOG_LEVEL` принимает оба словаря) |
| `service`    | `api`, `bot`, имя джобы                                                                                             |
| `event`      | `<домен>.<действие>`: `auth.login.ok`, `events.published`, `http.request`, `bot.update`                             |
| `msg`        | текст; для событий совпадает с `event`                                                                              |
| `request_id` | из `X-Request-ID` (ставит nginx) или сгенерированный; у джоб — id прогона                                           |
| `user_id`    | внутренний id пользователя, если известен                                                                           |
| `err`        | `{type, message, stack}` при исключении                                                                             |
| прочее       | поля события (`duration_ms`, `status`, `event_id`, …)                                                               |

## Куда пишется

- **stdout** контейнера: JSON (`LOG_FORMAT=json`, прод) или цветной однострочник
  (`pretty`, dev). `docker compose logs` ротируется по объёму (см. `x-logging`).
- **файл** `LOG_DIR/<service>.log`: всегда JSON, ротация раз в сутки по UTC,
  повёрнутые файлы `api.<дата>.log.gz` (Python) и `bot.<дата>.N.log` (pino-roll).
  `LOG_DIR=` (явно пусто) выключает файл и в core, и в боте. Хранение бессрочное:
  чистит человек, когда понадобится. В проде у каждого сервиса свой подкаталог
  `app_logs/<сервис>` с владельцем под uid контейнера.
- **gateway**: `app_logs/nginx/access-<дата>.log`, формат `maxapp_evidence` с полем
  `rid=$request_id` — тем же идентификатором, что `request_id` в core.

## Как пользоваться в коде

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

Правила: имя события — константа-строка `<домен>.<действие>`; поля — kwargs, не
интерполяция в текст; секреты и сырые initData в лог не кладутся; `request_id` и
`user_id` в Python подмешиваются из contextvars автоматически.

## Корреляция инцидента

1. Пользователь присылает `request_id` из ответа API (поле есть в каждой ошибке).
2. `grep <request_id> app_logs/api.log app_logs/nginx/access-*.log` — строка gateway
   (IP, статус, время) и строки core (кто, что делал, где упало).
3. Для событий бота — `event_id` из ответа `/admin/notify` совпадает с `event_id`
   в `events.published` (core) и `events.handled` / `notify.delivered` (бот).
