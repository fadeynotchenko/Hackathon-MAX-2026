"""Сессии через HTTP: детект кражи refresh переживает 401, cookie в проде, CSRF."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from core.api.main import create_app
from core.api.routers.auth import REFRESH_COOKIE
from core.api.state import ApiState
from core.config.app_config import AppConfig
from core.events import EventBus


async def test_reused_refresh_token_revokes_family_despite_401(
    client: AsyncClient, make_init_data
) -> None:
    await client.post("/api/v1/auth/max", json={"init_data": make_init_data(31)})
    stolen = client.cookies.get(REFRESH_COOKIE)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    fresh = client.cookies.get(REFRESH_COOKIE)
    assert fresh and fresh != stolen

    # Украденная (уже ротированная) копия → 401 и отзыв всей семьи.
    client.cookies.set(REFRESH_COOKIE, stolen, path="/api/v1/auth")
    replay = await client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401 and replay.json()["code"] == "auth.refresh.reused"

    # Отзыв закоммичен: свежий токен той же семьи тоже больше не работает.
    client.cookies.set(REFRESH_COOKIE, fresh, path="/api/v1/auth")
    after = await client.post("/api/v1/auth/refresh")
    assert after.status_code == 401 and after.json()["code"] == "auth.refresh.revoked"


async def test_logout_then_refresh_is_not_reported_as_theft(
    client: AsyncClient, make_init_data
) -> None:
    await client.post("/api/v1/auth/max", json={"init_data": make_init_data(32)})
    token = client.cookies.get(REFRESH_COOKIE)
    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    client.cookies.set(REFRESH_COOKIE, token, path="/api/v1/auth")
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401 and response.json()["code"] == "auth.refresh.revoked"


async def test_cross_site_requests_to_cookie_routes_are_rejected(
    client: AsyncClient, make_init_data
) -> None:
    await client.post("/api/v1/auth/max", json={"init_data": make_init_data(33)})
    for path in ("/api/v1/auth/refresh", "/api/v1/auth/logout"):
        response = await client.post(path, headers={"Sec-Fetch-Site": "cross-site"})
        assert response.status_code == 403 and response.json()["code"] == "auth.cross_site"
    # Свой origin (в том числе из фрейма веб-клиента MAX) — same-origin.
    assert (
        await client.post("/api/v1/auth/refresh", headers={"Sec-Fetch-Site": "same-origin"})
    ).status_code == 200


async def test_production_cookie_attributes(db: None, redis, auth_config, make_init_data) -> None:
    prod = AppConfig(
        env="production",
        log_level="INFO",
        public_base_url="https://example.tld",
        admin_max_ids=frozenset(),
        cors_allow_origins=(),
        request_timeout_seconds=5,
        dev_login_enabled=False,
    )
    app = create_app(app_config=prod, lifespan_factory=None, request_timeout_seconds=5)
    app.state.api = ApiState(
        app_config=prod,
        auth_config=auth_config,
        event_bus=EventBus(redis, stream_to_bot="t", source="test", maxlen=10),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        login = await c.post("/api/v1/auth/max", json={"init_data": make_init_data(34)})
        cookie = login.headers["set-cookie"]
        assert "SameSite=none" in cookie and "Secure" in cookie and "HttpOnly" in cookie
        logout = await c.post("/api/v1/auth/logout")
        cleared = logout.headers["set-cookie"]
        assert "Max-Age=0" in cleared and "SameSite=none" in cleared and "Secure" in cleared
