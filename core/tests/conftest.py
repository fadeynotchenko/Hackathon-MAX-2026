"""Общие фикстуры: окружение, SQLite in-memory вместо PostgreSQL, fakeredis вместо Redis.

Тесты не трогают настоящие сервисы: движок SQLAlchemy подменяется через
``db.base.use_session_maker``, Redis — через ``db.redis.use_redis``. Приложение
собирается фабрикой ``create_app`` без lifespan, состояние кладётся руками.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from fakeredis import aioredis as fakeredis_aio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Окружение задаётся ДО импорта модулей проекта: конфиги читают его при импорте.
os.environ.setdefault("ENV", "dev")
os.environ["LOG_DIR"] = ""
os.environ["LOG_FORMAT"] = "json"
os.environ.setdefault("MAX_BOT_TOKEN", "test-bot-token-0123456789abcdef")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-0123456789abcdef-0123456789")
os.environ.setdefault("ADMIN_MAX_IDS", "[777]")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")

from core.api.main import create_app
from core.api.state import ApiState
from core.config.app_config import AppConfig, reset_app_config
from core.db.base import close_db, get_session, use_session_maker
from core.db.models import Base
from core.db.redis import use_redis
from core.domain.initdata import build_init_data
from core.events import EventBus
from core.files import FilesConfig
from core.usecases.auth.config import AuthConfig

# Конфликтные копии облачной синхронизации («test_x 2.py») pytest подбирает как тесты.
collect_ignore_glob = ["**/* [0-9].py", "**/* [0-9][0-9].py"]

BOT_TOKEN = os.environ["MAX_BOT_TOKEN"]
ADMIN_MAX_ID = 777


@pytest.fixture
def bot_token() -> str:
    return BOT_TOKEN


@pytest.fixture
def auth_config(bot_token: str) -> AuthConfig:
    return AuthConfig(
        bot_token=bot_token,
        jwt_secret=os.environ["JWT_SECRET"],
        access_ttl_seconds=900,
        refresh_ttl_seconds=30 * 24 * 3600,
        init_data_max_age_seconds=86400,
    )


@pytest.fixture
def app_config() -> AppConfig:
    reset_app_config()
    return AppConfig(
        env="dev",
        log_level="INFO",
        public_base_url="http://localhost",
        admin_max_ids=frozenset({ADMIN_MAX_ID}),
        cors_allow_origins=(),
        request_timeout_seconds=5,
        dev_login_enabled=True,
    )


@pytest.fixture
def files_config(tmp_path) -> FilesConfig:
    """Файлы документов пишутся во временный каталог теста, а не в app_data."""
    return FilesConfig(
        documents_dir=tmp_path / "documents", soffice_bin="soffice", pdf_timeout_seconds=10
    )


@pytest.fixture
async def db() -> AsyncIterator[None]:
    """SQLite в памяти на один тест. StaticPool держит одно соединение — иначе
    каждая новая сессия получала бы пустую базу."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    use_session_maker(
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False), engine
    )
    yield
    await close_db()


@pytest.fixture
async def session(db: None) -> AsyncIterator[AsyncSession]:
    async with get_session() as s:
        yield s


@pytest.fixture
async def redis() -> AsyncIterator[fakeredis_aio.FakeRedis]:
    client = fakeredis_aio.FakeRedis(decode_responses=True)
    use_redis(client)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def make_init_data(bot_token: str):
    """Фабрика подписанных initData: make_init_data(user_id=1, first_name="A", ...)."""

    def _make(
        user_id: int = 1, *, first_name: str = "Test", auth_date: int | None = None, **user_extra
    ):
        import time

        params: dict[str, object] = {
            "query_id": f"q-{user_id}",
            "user": {"id": user_id, "first_name": first_name, "language_code": "ru", **user_extra},
            "auth_date": auth_date if auth_date is not None else int(time.time()),
        }
        return build_init_data(params, bot_token)

    return _make


@pytest.fixture
async def app(
    db: None,
    redis: fakeredis_aio.FakeRedis,
    app_config: AppConfig,
    auth_config: AuthConfig,
    files_config: FilesConfig,
):
    application = create_app(
        app_config=app_config, lifespan_factory=None, request_timeout_seconds=5
    )
    application.state.api = ApiState(
        app_config=app_config,
        auth_config=auth_config,
        event_bus=EventBus(redis, stream_to_bot="test:to_bot", source="api-test", maxlen=100),
        files_config=files_config,
    )
    return application


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
