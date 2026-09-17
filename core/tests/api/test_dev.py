"""Dev-вход: ручка есть только вне production, а её initData проходит настоящий /auth/max."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from core.api.main import create_app
from core.api.state import ApiState
from core.config.app_config import AppConfig
from core.events import EventBus
from tests.conftest import ADMIN_MAX_ID


async def test_dev_init_data_logs_in_as_first_admin(client: AsyncClient) -> None:
    response = await client.get("/api/v1/dev/init-data")
    assert response.status_code == 200
    body = response.json()
    assert body["max_user_id"] == ADMIN_MAX_ID and body["is_admin"] is True

    login = await client.post("/api/v1/auth/max", json={"init_data": body["init_data"]})
    assert login.status_code == 200
    assert login.json()["user"]["is_admin"] is True
    assert login.json()["user"]["username"] == "dev"


async def test_dev_init_data_custom_user(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/dev/init-data", params={"user_id": 5, "first_name": "Ann", "username": "ann"}
    )
    body = response.json()
    assert body["max_user_id"] == 5 and body["is_admin"] is False
    login = await client.post("/api/v1/auth/max", json={"init_data": body["init_data"]})
    assert login.status_code == 200 and login.json()["user"]["first_name"] == "Ann"


async def test_dev_route_is_absent_in_production(
    db: None, redis, app_config: AppConfig, auth_config
) -> None:
    prod = AppConfig(
        env="production",
        log_level="INFO",
        public_base_url="https://example.tld",
        admin_max_ids=frozenset(),
        cors_allow_origins=(),
        request_timeout_seconds=5,
        dev_login_enabled=True,
    )
    app = create_app(app_config=prod, lifespan_factory=None, request_timeout_seconds=5)
    app.state.api = ApiState(
        app_config=prod,
        auth_config=auth_config,
        event_bus=EventBus(redis, stream_to_bot="t", source="test", maxlen=10),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/v1/dev/init-data")).status_code == 404, (
            "в production dev-вход недоступен даже с флагом"
        )
        assert (await c.get("/api/v1/openapi.json")).status_code == 404, (
            "в production Swagger выключен"
        )
