"""Транзакция запроса закрыта до ответа и до фоновых задач.

SQLite в тестах живёт на одном соединении, поэтому незакоммиченное видно всем
сессиям, и опоздавший commit сам по себе здесь не проявится. Проверяется
порядок: к моменту фоновой задачи сессия запроса уже вне транзакции.
"""

from __future__ import annotations

from fastapi import BackgroundTasks
from httpx import AsyncClient
from sqlalchemy import text

from core.api.dependencies import SessionDep


async def test_request_session_commits_before_background_tasks(app, client: AsyncClient) -> None:
    seen: list[bool] = []

    @app.post("/test/commit-order")
    async def probe(session: SessionDep, background: BackgroundTasks) -> dict[str, bool]:
        await session.execute(text("SELECT 1"))
        background.add_task(lambda: seen.append(session.in_transaction()))
        return {"ok": True}

    response = await client.post("/test/commit-order")
    assert response.status_code == 200
    assert seen == [False], "фоновая задача застала открытую транзакцию запроса"
