"""Точка входа API: ``uvicorn core.api.main:app``.

Порядок middleware: последний добавленный — внешний. Снаружи внутрь:
CORS → RequestContext (request_id, access-лог) → Timeout → роутеры.
Volumetric rate-limit живёт в nginx (limit_req), здесь его нет намеренно:
per-worker счётчики в приложении не складываются между воркерами.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.api.error_handlers import register_exception_handlers
from core.api.events_worker import WorkerDeps, run_events_worker
from core.api.middlewares import RequestContextMiddleware, TimeoutMiddleware
from core.api.routers import (
    admin,
    agent,
    auth,
    counterparties,
    dev,
    documents,
    health,
    me,
    organizations,
    templates,
)
from core.api.state import ApiState
from core.config.app_config import AppConfig, get_app_config
from core.config.env_spec import validate_env_or_raise
from core.db import close_db, close_redis, get_session, init_db, init_redis, new_client
from core.db.config import DatabaseConfig
from core.db.migrate import upgrade_to_head
from core.db.redis import RedisConfig
from core.events import EventBus, get_events_config
from core.files import FilesConfig
from core.llm import GigaChatConfig, build_llm_client
from core.logs import biz_error, biz_info, biz_warn, setup_logging
from core.usecases.auth.config import get_auth_config
from core.usecases.documents import ensure_builtin_templates

API_V1_PREFIX = "/api/v1"
logger = logging.getLogger("api")

_DEV_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _report_worker_exit(task: asyncio.Task[None]) -> None:
    """Потребитель событий умер (Redis недоступен, ошибка группы): без этого
    /health показывал бы events_worker=error, а причины в логах не было бы."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        biz_error(logger, "events.worker.crashed", error=str(exc), exc_info=exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app_config = get_app_config()
    setup_logging("api", level=app_config.log_level)
    report = validate_env_or_raise("api")
    biz_info(logger, "api.env.validated", checked=report.checked)

    db_config = DatabaseConfig.from_env()
    db_config.validate()
    # Схема приводится к head до открытия пула: процесс не обслуживает запросы
    # на недомигрированной базе. Несколько воркеров сериализует advisory-lock.
    await upgrade_to_head()
    await init_db(db_config)
    # Библиотека шаблонов должна существовать до первого запроса: три встроенных
    # шаблона дешевле засеять здесь, чем заводить ради них контейнер-сеятель.
    async with get_session() as session:
        seeded = await ensure_builtin_templates(session)
    biz_info(logger, "templates.seeded", count=seeded)
    redis = await init_redis(RedisConfig.from_env())

    events = get_events_config()
    llm = build_llm_client(GigaChatConfig.from_env())
    if llm is None:
        # Без ключа приложение работает, но про выключенного агента должно быть видно в логе старта.
        biz_warn(logger, "agent.disabled", reason="GIGACHAT_AUTH_KEY is empty")
    app.state.api = ApiState(
        app_config=app_config,
        auth_config=get_auth_config(),
        files_config=FilesConfig.from_env(),
        llm=llm,
        event_bus=EventBus(
            redis, stream_to_bot=events.stream_to_bot, source="api", maxlen=events.maxlen
        ),
    )
    # Потребитель событий бота живёт в этом же процессе; отдельное соединение,
    # чтобы блокирующий XREADGROUP не держал очередь команд запросов API.
    worker_redis = new_client(RedisConfig.from_env())
    stop = asyncio.Event()
    worker_deps = WorkerDeps(
        redis=redis,
        bus=app.state.api.event_bus,
        files=app.state.api.files_config,
        llm=llm,
    )
    app.state.events_task = asyncio.create_task(
        run_events_worker(worker_redis, stream=events.stream_to_core, stop=stop, deps=worker_deps),
        name="events-worker",
    )
    app.state.events_task.add_done_callback(_report_worker_exit)
    if app_config.dev_login_enabled and not app_config.is_production:
        # Dev-вход выдаёт сессию любому user_id без подписи клиента MAX: в логе
        # старта это должно быть видно.
        biz_warn(logger, "api.dev_login.enabled", route=f"{API_V1_PREFIX}/dev/init-data")
    biz_info(logger, "api.started", env=app_config.env)
    try:
        yield
    finally:
        stop.set()
        try:
            await asyncio.wait_for(app.state.events_task, timeout=10)
        except TimeoutError:
            biz_warn(logger, "events.worker.stop_timeout")
            app.state.events_task.cancel()
        except asyncio.CancelledError:
            app.state.events_task.cancel()
            raise
        except Exception:  # noqa: S110 — причина уже записана _report_worker_exit
            pass
        await worker_redis.aclose()
        if llm is not None:
            await llm.aclose()
        await close_redis()
        await close_db()
        biz_info(logger, "api.stopped")


def cors_origins(app_config: AppConfig) -> list[str]:
    """В проде мини-апп и API на одном origin (nginx), CORS нужен только для
    явно перечисленных адресов. Localhost-порты vite разрешены вне production."""
    origins: list[str] = [] if app_config.is_production else list(_DEV_ORIGINS)
    origins.extend(o for o in app_config.cors_allow_origins if o not in origins)
    return origins


def create_app(
    *,
    app_config: AppConfig | None = None,
    lifespan_factory: Callable[[FastAPI], AsyncIterator[None]] | None = lifespan,
    request_timeout_seconds: float | None = None,
) -> FastAPI:
    """Фабрика приложения. Тесты передают ``lifespan_factory=None`` и заполняют
    ``app.state.api`` сами (SQLite + fakeredis)."""
    config = app_config or get_app_config()
    docs_enabled = not config.is_production
    app = FastAPI(
        title="MAX mini app API",
        version="0.1.0",
        lifespan=lifespan_factory,
        docs_url=f"{API_V1_PREFIX}/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url=f"{API_V1_PREFIX}/openapi.json" if docs_enabled else None,
    )

    app.add_middleware(
        TimeoutMiddleware, timeout_seconds=request_timeout_seconds or config.request_timeout_seconds
    )
    app.add_middleware(RequestContextMiddleware)
    origins = cors_origins(config)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )

    for router in (
        health.router,
        auth.router,
        me.router,
        admin.router,
        templates.router,
        documents.router,
        agent.router,
        agent.requisites_router,
        counterparties.router,
        organizations.router,
    ):
        app.include_router(router, prefix=API_V1_PREFIX)
    # Dev-вход — явный opt-in (DEV_LOGIN_ENABLED) и никогда в production: в проде
    # пути нет вовсе, а не «закрыт». «Не production» само по себе ничего не включает.
    if config.dev_login_enabled and not config.is_production:
        app.include_router(dev.router, prefix=API_V1_PREFIX)

    register_exception_handlers(app)
    return app


app = create_app()
