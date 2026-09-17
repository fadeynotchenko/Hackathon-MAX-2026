from __future__ import annotations

from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}
    assert response.headers["x-request-id"]


async def test_health_degraded_when_redis_down(client: AsyncClient, redis, monkeypatch) -> None:
    async def broken_ping():
        raise ConnectionError("redis down")

    monkeypatch.setattr("core.api.routers.health.ping_redis", broken_ping)
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "error"


async def test_health_reports_events_worker(client: AsyncClient, app) -> None:
    import asyncio

    async def forever():
        await asyncio.Event().wait()

    task = asyncio.create_task(forever())
    app.state.events_task = task
    try:
        assert (await client.get("/api/v1/health")).json()["checks"]["events_worker"] == "ok"
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        response = await client.get("/api/v1/health")
        assert response.status_code == 503 and response.json()["checks"]["events_worker"] == "error"
    finally:
        del app.state.events_task
