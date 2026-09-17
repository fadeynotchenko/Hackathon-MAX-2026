"""HTTP-контракт: вход, cookie, /me, refresh, logout, админ-ручки, формат ошибок."""

from __future__ import annotations

from httpx import AsyncClient

from core.api.routers.auth import REFRESH_COOKIE
from tests.conftest import ADMIN_MAX_ID


async def _login(client: AsyncClient, make_init_data, user_id: int = 1, **kw) -> dict:
    response = await client.post(
        "/api/v1/auth/max", json={"init_data": make_init_data(user_id, **kw)}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_login_sets_cookie_and_returns_session(client: AsyncClient, make_init_data) -> None:
    response = await client.post(
        "/api/v1/auth/max", json={"init_data": make_init_data(1, first_name="Ann")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    assert body["user"]["max_user_id"] == 1 and body["user"]["first_name"] == "Ann"
    assert body["user"]["is_admin"] is False
    cookie = response.headers["set-cookie"]
    assert (
        cookie.startswith(f"{REFRESH_COOKIE}=")
        and "HttpOnly" in cookie
        and "Path=/api/v1/auth" in cookie
    )
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie, "в dev cookie без Secure, иначе http://localhost её не примет"


async def test_login_rejects_bad_init_data(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/max", json={"init_data": "auth_date=1&hash=bad"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "auth.init_data.bad_signature" and body["request_id"]


async def test_validation_error_format(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/max", json={})
    assert response.status_code == 422
    assert response.json()["code"] == "validation"


async def test_me_requires_token(client: AsyncClient, make_init_data) -> None:
    assert (await client.get("/api/v1/me")).json()["code"] == "auth.missing_token"
    assert (
        await client.get("/api/v1/me", headers={"Authorization": "Bearer nope"})
    ).status_code == 401
    session = await _login(client, make_init_data, 3, first_name="Bob")
    response = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {session['access_token']}"}
    )
    assert response.status_code == 200 and response.json()["display_name"] == "Bob"


async def test_refresh_and_logout(client: AsyncClient, make_init_data) -> None:
    await _login(client, make_init_data, 4)
    first_cookie = client.cookies.get(REFRESH_COOKIE)
    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200 and refreshed.json()["access_token"]
    assert client.cookies.get(REFRESH_COOKIE) != first_cookie

    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    assert client.cookies.get(REFRESH_COOKIE) is None
    missing = await client.post("/api/v1/auth/refresh")
    assert missing.status_code == 401 and missing.json()["code"] == "auth.refresh.missing"


async def test_admin_routes(client: AsyncClient, make_init_data, redis) -> None:
    user = await _login(client, make_init_data, 5)
    forbidden = await client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {user['access_token']}"}
    )
    assert forbidden.status_code == 403 and forbidden.json()["code"] == "auth.not_admin"

    admin = await _login(client, make_init_data, ADMIN_MAX_ID, first_name="Root")
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    stats = await client.get("/api/v1/admin/stats", headers=headers)
    assert stats.status_code == 200
    body = stats.json()
    assert body == {"users_total": 2, "users_active_24h": 2}

    notify = await client.post(
        "/api/v1/admin/notify",
        headers=headers,
        json={"max_user_id": 5, "text": "hello", "format": "markdown"},
    )
    assert notify.status_code == 202
    event_id = notify.json()["event_id"]
    entries = await redis.xrange("test:to_bot")
    assert len(entries) == 1
    fields = entries[0][1]
    assert fields["id"] == event_id, "наружу уходит UUID события, а не stream id"
    assert fields["type"] == "notify.user" and fields["source"] == "api-test" and fields["v"] == "1"
    assert '"max_user_id":5' in fields["payload"] and '"text":"hello"' in fields["payload"]


async def test_request_id_is_propagated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"
    injected = await client.get(
        "/api/v1/health", headers={"X-Request-ID": "bad\nvalue with spaces"}
    )
    assert injected.headers["x-request-id"] == "badvaluewithspaces"


async def test_openapi_is_served_in_dev(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/auth/max" in paths and "/api/v1/me" in paths
