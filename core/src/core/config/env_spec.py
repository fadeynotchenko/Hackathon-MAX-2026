"""Декларативный реестр ВСЕХ переменных окружения проекта.

Одно место, где видно каждую переменную стека (core, bot, web, compose): тип,
дефолт, кому обязательна, кто читает. Это метаданные, а не чтение env: значения
читают владельцы через ``core.config.env`` (Python) и zod-схему бота.

Потребители:
- ``validate_env_or_raise(layer)`` — стартовый валидатор процесса api
  (``core.api.main``): один отчёт «чего не хватает».
- ``core.scripts.gen_env_example`` — генерирует корневой ``.env.example``.
- ``tests/config/test_env_spec.py`` — целостность реестра, синхронность с
  ``.env.example``, compose-файлами и zod-схемой бота.

Правило: добавил чтение переменной в код — добавь запись сюда и перегенерируй
``.env.example``. Тест-замок не даст забыть.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from core.config.env import get_env

# Слои-потребители. Обязательность моделируется по слоям: одна переменная может
# быть обязательной для api и безразличной для джобы.
API = "api"  # процесс core: HTTP, миграции при старте, потребитель событий
BOT = "bot"  # TypeScript-сервис, валидирует своей zod-схемой (bot/src/config.ts)
WEB = "web"  # build-time (Vite), Python-валидатором не проверяется
COMPOSE = "compose"  # читается только docker compose / nginx / deploy.sh

PYTHON_LAYERS = frozenset({API})
ALL_LAYERS = PYTHON_LAYERS | {BOT, WEB, COMPOSE}

T_STR = "str"
T_INT = "int"
T_BOOL = "bool"
T_URL = "url"
T_LIST = "list"  # JSON-массив или CSV
T_SECRET = "secret"  # noqa: S105 — имя типа, не пароль
VALID_TYPES = frozenset({T_STR, T_INT, T_BOOL, T_URL, T_LIST, T_SECRET})


@dataclass(frozen=True)
class EnvVar:
    name: str
    description: str
    type: str = T_STR
    group: str = ""
    required_for: frozenset[str] = field(default_factory=frozenset)
    default: str | None = None
    example: str | None = None
    owner: str = ""
    notes: str = ""

    @property
    def secret(self) -> bool:
        return self.type == T_SECRET


def _req(*layers: str) -> frozenset[str]:
    return frozenset(layers)


def _grouped(group: str, *variables: EnvVar) -> list[EnvVar]:
    return [replace(v, group=group) for v in variables]


GROUP_ORDER: tuple[str, ...] = (
    "environment",
    "max",
    "bot",
    "database",
    "redis",
    "auth",
    "api",
    "events",
    "documents",
    "agent",
    "backup",
    "ports",
    "web",
)

GROUP_TITLES: dict[str, str] = {
    "environment": "Окружение / логи",
    "max": "Платформа MAX",
    "bot": "Бот (TypeScript)",
    "database": "PostgreSQL",
    "redis": "Redis",
    "auth": "Аутентификация мини-аппа",
    "api": "API",
    "events": "Шина событий (Redis Streams)",
    "documents": "Документы: файлы, конвертация и распознавание",
    "agent": "Помощник на GigaChat",
    "backup": "Бэкапы и деплой",
    "ports": "Порты на хосте (compose)",
    "web": "Мини-апп (build-time, Vite)",
}

ENV_SPEC: list[EnvVar] = [
    *_grouped(
        "environment",
        EnvVar(
            "ENV",
            "Имя окружения; production ⇒ прод-режим (secure-cookie, без CORS для localhost).",
            default="dev",
            owner="core.config.app_config; bot/src/config.ts",
        ),
        EnvVar(
            "LOG_LEVEL",
            "Уровень логирования.",
            default="INFO",
            owner="core.logs.setup; bot/src/logger.ts",
        ),
        EnvVar(
            "LOG_FORMAT",
            "Формат логов: auto (json вне TTY, pretty в терминале) | json | pretty.",
            default="auto",
            owner="core.logs.setup; bot/src/logger.ts",
        ),
        EnvVar(
            "LOG_DIR",
            "Каталог файловых логов (посуточная ротация, gzip). Пусто ⇒ только stdout.",
            default="app_logs",
            owner="core.logs.setup; bot/src/logger.ts",
        ),
        EnvVar(
            "PUBLIC_BASE_URL",
            "Публичный https-адрес стенда. Нужен боту в режиме webhook и для ссылок.",
            type=T_URL,
            example="https://maxapp.example.tld",
            owner="bot/src/config.ts; AppConfig",
        ),
        EnvVar(
            "DOMAIN",
            "Доменное имя для server_name nginx (прод-compose).",
            required_for=_req(COMPOSE),
            example="maxapp.example.tld",
            owner="gateway/templates/default.conf.template",
        ),
    ),
    *_grouped(
        "max",
        EnvVar(
            "MAX_BOT_TOKEN",
            "Токен бота от MasterBot. Один и тот же секрет подписывает initData мини-аппа.",
            type=T_SECRET,
            required_for=_req(API, BOT),
            example="dev-only-bot-token-replace-with-masterbot-token",
            notes="С плейсхолдером мини-апп на локали работает (dev-вход), бот — нет: MAX ответит 401.",
            owner="core.usecases.auth.config; bot/src/config.ts",
        ),
        EnvVar(
            "MAX_MINI_APP_NAME",
            "Имя мини-приложения для кнопки open_app; у бота совпадает с его username.",
            owner="bot/src/config.ts",
            notes="Пусто ⇒ кнопка не показывается: MAX отвечает 400 «Field 'webApp' cannot be null» и теряет всё сообщение.",
        ),
        EnvVar(
            "ADMIN_MAX_IDS",
            "Список user_id администраторов (JSON-массив или CSV).",
            type=T_LIST,
            default="[]",
            example="[123456789]",
            owner="core.config.app_config",
        ),
    ),
    *_grouped(
        "bot",
        EnvVar(
            "CORE_INTERNAL_URL",
            "Адрес API ядра внутри стека: бот забирает по нему файлы документов.",
            type=T_URL,
            default="http://api:8000",
            owner="bot/src/config.ts",
        ),
        EnvVar(
            "BOT_MODE",
            "polling (dev) | webhook (прод за nginx).",
            default="polling",
            owner="bot/src/config.ts",
        ),
        EnvVar(
            "BOT_WEBHOOK_PATH",
            "Путь вебхука; nginx проксирует его в контейнер бота.",
            default="/bot/webhook",
            owner="bot/src/config.ts; gateway/templates/default.conf.template",
        ),
        EnvVar(
            "BOT_WEBHOOK_SECRET",
            "Секрет вебхука: MAX присылает его в заголовке x-max-bot-api-secret.",
            type=T_SECRET,
            example="dev-only-webhook-secret-0123456789",
            owner="bot/src/config.ts",
            notes="Обязателен при BOT_MODE=webhook (проверяет zod-схема бота).",
        ),
        EnvVar(
            "BOT_WEBHOOK_PORT",
            "Порт HTTP-сервера вебхука внутри контейнера.",
            type=T_INT,
            default="8080",
            owner="bot/src/config.ts",
        ),
        EnvVar(
            "BOT_HEALTH_PORT",
            "Порт эндпоинта /health бота (docker healthcheck).",
            type=T_INT,
            default="8081",
            owner="bot/src/health.ts",
        ),
        EnvVar(
            "BOT_SESSION_TTL_SECONDS",
            "TTL сессии пользователя в Redis.",
            type=T_INT,
            default="604800",
            owner="bot/src/session/redis-store.ts",
        ),
    ),
    *_grouped(
        "database",
        EnvVar(
            "DB_HOST",
            "Хост PostgreSQL (в compose — сервис db).",
            default="db",
            owner="core.db.config",
        ),
        EnvVar("DB_PORT", "Порт PostgreSQL.", type=T_INT, default="5432", owner="core.db.config"),
        EnvVar(
            "DB_USER",
            "Пользователь БД.",
            required_for=_req(API, COMPOSE),
            example="maxapp",
            owner="core.db.config; docker-compose (POSTGRES_USER)",
        ),
        EnvVar(
            "DB_PASSWORD",
            "Пароль БД.",
            type=T_SECRET,
            required_for=_req(API, COMPOSE),
            example="dev-only-db-password",
            owner="core.db.config; docker-compose (POSTGRES_PASSWORD)",
        ),
        EnvVar(
            "DB_NAME",
            "Имя БД.",
            required_for=_req(API, COMPOSE),
            example="maxapp",
            owner="core.db.config; docker-compose (POSTGRES_DB)",
        ),
        EnvVar(
            "DB_POOL_SIZE",
            "Размер пула соединений на процесс.",
            type=T_INT,
            default="5",
            owner="core.db.config",
        ),
        EnvVar(
            "DB_MAX_OVERFLOW",
            "Overflow-соединения сверх пула.",
            type=T_INT,
            default="10",
            owner="core.db.config",
        ),
        EnvVar(
            "DB_POOL_TIMEOUT",
            "Ожидание свободного соединения из пула (сек).",
            type=T_INT,
            default="10",
            owner="core.db.config",
        ),
        EnvVar(
            "DB_POOL_RECYCLE",
            "Пересоздание соединения (сек).",
            type=T_INT,
            default="1800",
            owner="core.db.config",
        ),
        EnvVar(
            "DB_STATEMENT_TIMEOUT_MS",
            "statement_timeout PostgreSQL (мс).",
            type=T_INT,
            default="30000",
            owner="core.db.config",
        ),
        EnvVar(
            "TEST_DATABASE_URL",
            "DSN тестового PostgreSQL для tests/integration (docker-compose.test.yml).",
            type=T_URL,
            example="postgresql+asyncpg://maxapp:maxapp@localhost:5544/maxapp_test",
            owner="core/tests (integration)",
            notes="Только для тестов.",
        ),
    ),
    *_grouped(
        "redis",
        EnvVar(
            "REDIS_HOST",
            "Хост Redis (в compose — сервис redis).",
            default="redis",
            owner="core.db.redis; bot/src/config.ts",
        ),
        EnvVar(
            "REDIS_PORT",
            "Порт Redis.",
            type=T_INT,
            default="6379",
            owner="core.db.redis; bot/src/config.ts",
        ),
        EnvVar(
            "REDIS_PASSWORD",
            "Пароль Redis (прод-compose поднимает redis с --requirepass).",
            type=T_SECRET,
            required_for=_req(COMPOSE),
            example="dev-only-redis-password",
            owner="core.db.redis; bot/src/config.ts; docker-compose.prod.yml",
        ),
        EnvVar(
            "REDIS_DB",
            "Номер логической БД Redis.",
            type=T_INT,
            default="0",
            owner="core.db.redis; bot/src/config.ts",
        ),
        EnvVar(
            "TEST_REDIS_URL",
            "URL тестового Redis для tests/integration.",
            type=T_URL,
            example="redis://localhost:6544/0",
            owner="core/tests (integration)",
            notes="Только для тестов.",
        ),
    ),
    *_grouped(
        "auth",
        EnvVar(
            "JWT_SECRET",
            "Секрет подписи access-токенов (не короче 32 символов).",
            type=T_SECRET,
            required_for=_req(API),
            example="dev-only-jwt-secret-change-in-production-0123456789",
            notes="Сгенерировать: openssl rand -hex 32.",
            owner="core.usecases.auth.config",
        ),
        EnvVar(
            "ACCESS_TOKEN_TTL_SECONDS",
            "Время жизни access-токена.",
            type=T_INT,
            default="900",
            owner="core.usecases.auth.config",
        ),
        EnvVar(
            "REFRESH_TOKEN_TTL_SECONDS",
            "Время жизни refresh-токена (cookie).",
            type=T_INT,
            default="2592000",
            owner="core.usecases.auth.config",
        ),
        EnvVar(
            "INIT_DATA_MAX_AGE_SECONDS",
            "Максимальный возраст initData мини-аппа (auth_date). Утёкшая строка initData даёт вход всё это время.",
            type=T_INT,
            default="3600",
            owner="core.usecases.auth.config",
        ),
        EnvVar(
            "DEV_LOGIN_ENABLED",
            "Ручка GET /dev/init-data (вход тестовым пользователем без клиента MAX). Только dev-стенд.",
            type=T_BOOL,
            default="false",
            owner="core.config.app_config; core.api.main",
            notes="В production запрещена валидатором: с ней любой получает сессию любого пользователя.",
        ),
        EnvVar(
            "CORS_ALLOW_ORIGINS",
            "Дополнительные CORS-origin'ы (CSV). В dev localhost разрешён и так.",
            type=T_LIST,
            owner="core.config.app_config; core.api.main",
        ),
    ),
    *_grouped(
        "api",
        EnvVar(
            "API_REQUEST_TIMEOUT_SECONDS",
            "Серверный таймаут одного HTTP-запроса (504 при превышении).",
            type=T_INT,
            default="30",
            owner="api/middlewares/timeout.py",
        ),
        EnvVar(
            "API_WORKERS",
            "Число uvicorn-воркеров в проде.",
            type=T_INT,
            default="1",
            owner="docker-compose.prod.yml",
            notes="Больше одного — только с LOG_DIR= (файл-лог не умеет ротироваться из нескольких процессов; логи тогда через docker stdout).",
        ),
    ),
    *_grouped(
        "events",
        EnvVar(
            "EVENTS_STREAM_TO_BOT",
            "Redis Stream событий ядро → бот (notify.user и т.п.).",
            default="maxapp:to_bot",
            owner="core.events.config; bot/src/config.ts",
        ),
        EnvVar(
            "EVENTS_STREAM_TO_CORE",
            "Redis Stream событий бот → core (bot.user_started и т.п.); читает воркер внутри api.",
            default="maxapp:to_core",
            owner="core.events.config; bot/src/config.ts",
        ),
        EnvVar(
            "EVENTS_STREAM_MAXLEN",
            "Приблизительная длина стрима (XADD MAXLEN ~).",
            type=T_INT,
            default="10000",
            owner="core.events.config; bot/src/config.ts",
        ),
    ),
    *_grouped(
        "documents",
        EnvVar(
            "DOCUMENTS_DIR",
            "Каталог готовых файлов документов (том контейнера).",
            default="app_data/documents",
            owner="core.files.config",
        ),
        EnvVar(
            "LIBREOFFICE_BIN",
            "Команда LibreOffice для конвертации DOCX → PDF.",
            default="soffice",
            owner="core.files.pdf",
            notes="Нет в PATH ⇒ PDF отдаётся ошибкой render.pdf_unavailable, DOCX продолжает работать.",
        ),
        EnvVar(
            "WITH_PDF",
            "Собирать образ core с LibreOffice (конвертация DOCX → PDF) на локальном стенде.",
            type=T_BOOL,
            default="false",
            owner="compose.yaml (build arg)",
            notes="Прод собирается с WITH_PDF=true всегда; локально false держит сборку быстрой.",
        ),
        EnvVar(
            "PDF_TIMEOUT_SECONDS",
            "Таймаут одной конвертации в PDF.",
            type=T_INT,
            default="60",
            owner="core.files.pdf",
        ),
        EnvVar(
            "MEDIA_MAX_BYTES",
            "Предел размера фото, скана или голосового на распознавание, байт.",
            type=T_INT,
            default="10485760",
            owner="core.files.config",
            notes="Больше ⇒ 413 media.too_large. Лимит gateway на эти ручки держать не ниже.",
        ),
        EnvVar(
            "MEDIA_DOWNLOAD_TIMEOUT_SECONDS",
            "Таймаут скачивания вложения, присланного боту, из хранилища MAX.",
            type=T_INT,
            default="30",
            owner="core.files.inbound",
        ),
    ),
    *_grouped(
        "agent",
        EnvVar(
            "GIGACHAT_AUTH_KEY",
            "Ключ авторизации GigaChat API (Base64 от Client ID и Client Secret из личного кабинета).",
            type=T_SECRET,
            owner="core.llm.config",
            notes="Пусто ⇒ помощник выключен: его ручки отвечают 503 agent.unavailable, остальное работает.",
        ),
        EnvVar(
            "GIGACHAT_SCOPE",
            "Версия API по типу доступа: GIGACHAT_API_PERS (физлица), GIGACHAT_API_B2B, GIGACHAT_API_CORP.",
            default="GIGACHAT_API_PERS",
            owner="core.llm.config",
        ),
        EnvVar(
            "GIGACHAT_MODEL",
            "Модель GigaChat для помощника.",
            default="GigaChat-3-Ultra",
            owner="core.llm.config",
        ),
        EnvVar(
            "GIGACHAT_API_URL",
            "Базовый адрес GigaChat API (chat/completions).",
            type=T_URL,
            default="https://api.giga.chat/v1",
            owner="core.llm.config",
        ),
        EnvVar(
            "GIGACHAT_AUTH_URL",
            "Адрес выдачи токена доступа GigaChat (OAuth).",
            type=T_URL,
            default="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            owner="core.llm.config",
        ),
        EnvVar(
            "GIGACHAT_CA_BUNDLE",
            "Корневой сертификат НУЦ Минцифры относительно каталога core.",
            default="certs/russian_trusted_root_ca.pem",
            owner="core.llm.config",
        ),
        EnvVar(
            "GIGACHAT_TIMEOUT_SECONDS",
            "Таймаут одного запроса к GigaChat.",
            type=T_INT,
            default="20",
            notes="Меньше API_REQUEST_TIMEOUT_SECONDS: иначе зависший ответ модели обрывается общим 504, а не ответом «помощник не отвечает».",
            owner="core.llm.config",
        ),
        EnvVar(
            "GIGACHAT_MAX_CONCURRENCY",
            "Сколько запросов к GigaChat один процесс api держит одновременно; остальные ждут в очереди.",
            type=T_INT,
            default="1",
            notes="Тариф физлиц (GIGACHAT_API_PERS) — один поток: второй параллельный запрос получает 429. Поднимать по лимиту своего тарифа.",
            owner="core.llm.config",
        ),
    ),
    *_grouped(
        "backup",
        EnvVar(
            "DB_BACKUP_HOUR_UTC",
            "Час UTC суточного pg_dump в проде.",
            type=T_INT,
            default="3",
            owner="docker-compose.prod.yml (db_backup)",
        ),
        EnvVar(
            "DB_BACKUP_KEEP",
            "Сколько суточных дампов хранить.",
            type=T_INT,
            default="14",
            owner="docker-compose.prod.yml (db_backup)",
        ),
        EnvVar(
            "PREDEPLOY_KEEP",
            "Сколько predeploy-снимков хранить.",
            type=T_INT,
            default="10",
            owner="deploy.sh",
        ),
        EnvVar(
            "SKIP_TESTS",
            "1 ⇒ deploy.sh не гоняет тесты перед выкаткой (только если они зелёные в CI).",
            type=T_BOOL,
            default="0",
            owner="deploy.sh",
            notes="Читается только скриптом деплоя, в .env не нужна.",
        ),
    ),
    *_grouped(
        "ports",
        EnvVar(
            "GATEWAY_HTTP_PORT",
            "HTTP-порт gateway на хосте (только прод: ACME http-01 и редирект на https).",
            type=T_INT,
            default="80",
            owner="docker-compose.prod.yml (gateway)",
        ),
        EnvVar(
            "GATEWAY_HTTPS_PORT",
            "HTTPS-порт gateway на хосте (только прод).",
            type=T_INT,
            default="443",
            owner="docker-compose.prod.yml (gateway)",
        ),
        EnvVar(
            "DEV_API_PORT",
            "Порт API на хосте в dev (мини-апп ходит через vite-proxy, это прямой доступ).",
            type=T_INT,
            default="8091",
            owner="compose.yaml (api)",
        ),
        EnvVar(
            "DEV_WEB_PORT",
            "Порт мини-аппа (vite dev-server) на хосте в dev: http://localhost:<порт>.",
            type=T_INT,
            default="3090",
            owner="compose.yaml (web)",
        ),
        EnvVar(
            "DEV_DB_PORT",
            "Порт PostgreSQL на хосте в dev.",
            type=T_INT,
            default="5490",
            owner="compose.yaml (db)",
        ),
        EnvVar(
            "DEV_REDIS_PORT",
            "Порт Redis на хосте в dev.",
            type=T_INT,
            default="6490",
            owner="compose.yaml (redis)",
        ),
    ),
    *_grouped(
        "web",
        EnvVar(
            "VITE_API_BASE_URL",
            "База API для мини-аппа. Пусто ⇒ same-origin (/api/v1 через nginx или vite-proxy).",
            owner="web/src/api/client.ts",
        ),
        EnvVar(
            "VITE_PROXY_TARGET",
            "Куда vite dev-server проксирует /api/ (в docker — http://api:8000).",
            type=T_URL,
            default="http://localhost:8000",
            owner="web/vite.config.ts",
        ),
        EnvVar(
            "VITE_DEV_INIT_DATA",
            "Подписанный initData для запуска мини-аппа в обычном браузере (dev).",
            owner="web/src/max/webapp.ts",
            notes="Сгенерировать: uv run python -m core.scripts.dev_init_data. Только dev.",
        ),
    ),
]

_BY_NAME: dict[str, EnvVar] = {v.name: v for v in ENV_SPEC}


def spec_for(name: str) -> EnvVar | None:
    return _BY_NAME.get(name)


def default_for(name: str) -> str:
    var = _BY_NAME[name]
    return var.default or ""


def _type_error(var: EnvVar, raw: str) -> str | None:
    """Текст ошибки типа для непустого значения, либо None."""
    if var.type == T_INT:
        try:
            int(raw)
        except ValueError:
            return f"{var.name}: ожидалось целое, получено {raw!r}"
    elif var.type == T_BOOL:
        if raw.lower() not in {"1", "0", "true", "false", "yes", "no", "on", "off"}:
            return f"{var.name}: ожидалось true/false, получено {raw!r}"
    elif var.type == T_URL:
        if not raw.startswith(("http://", "https://", "postgresql", "redis://")):
            return f"{var.name}: ожидался URL, получено {raw!r}"
    elif var.type == T_LIST and raw.startswith("["):
        try:
            json.loads(raw)
        except json.JSONDecodeError:
            return f"{var.name}: невалидный JSON-массив"
    return None


@dataclass
class EnvReport:
    layer: str
    missing: list[EnvVar] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.missing and not self.invalid

    def format(self) -> str:
        if self.ok:
            return f"env[{self.layer}]: проверено {self.checked} переменных, всё на месте"
        lines = [f"env[{self.layer}]: конфигурация неполная"]
        for var in self.missing:
            lines.append(f"  отсутствует {var.name} — {var.description}")
        lines.extend(f"  {msg}" for msg in self.invalid)
        return "\n".join(lines)


class EnvValidationError(RuntimeError):
    pass


# Плейсхолдеры из .env.example: с ними стек поднимается на локали без ручной
# генерации секретов, но в production они запрещены — валидатор не даст стартовать.
DEV_ONLY_PREFIX = "dev-only-"


def validate_env(layer: str) -> EnvReport:
    """Проверить окружение для слоя: обязательные присутствуют, типы валидны,
    в production нет dev-плейсхолдеров."""
    if layer not in PYTHON_LAYERS:
        raise ValueError(f"unknown python layer {layer!r}; expected one of {sorted(PYTHON_LAYERS)}")
    report = EnvReport(layer=layer)
    production = get_env("ENV", default_for("ENV")).lower() == "production"
    for var in ENV_SPEC:
        raw = get_env(var.name)
        if not raw:
            if layer in var.required_for:
                report.missing.append(var)
            continue
        report.checked += 1
        error = _type_error(var, raw)
        if error:
            report.invalid.append(error)
        elif production and var.secret and raw.startswith(DEV_ONLY_PREFIX):
            report.invalid.append(f"{var.name}: dev-плейсхолдер из .env.example в production")
        elif (
            production
            and var.name == "DEV_LOGIN_ENABLED"
            and raw.lower() in {"1", "true", "yes", "on"}
        ):
            report.invalid.append("DEV_LOGIN_ENABLED: dev-вход в production запрещён")
    return report


def validate_env_or_raise(layer: str) -> EnvReport:
    """Fail-fast на старте: работать с неполной конфигурацией нельзя."""
    report = validate_env(layer)
    if not report.ok:
        raise EnvValidationError(report.format())
    return report
