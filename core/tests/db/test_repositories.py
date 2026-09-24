from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import (
    RefreshTokenRepository,
    UserRepository,
    UserUpsert,
)


async def test_user_upsert_and_counts(session: AsyncSession) -> None:
    repo = UserRepository(session)
    user = await repo.upsert_from_max(
        UserUpsert(max_user_id=10, first_name="A", via="bot"),
        touch_login=False,
        now=datetime.now(UTC),
    )
    assert user.id is not None and user.first_seen_via == "bot" and user.last_login_at is None
    same = await repo.upsert_from_max(
        UserUpsert(max_user_id=10, first_name="B", username="b"),
        touch_login=True,
        now=datetime.now(UTC),
    )
    assert same.id == user.id and same.first_name == "B" and same.last_login_at is not None
    assert same.first_seen_via == "bot", "источник первого визита не перезаписывается"
    assert await repo.count() == 1
    assert await repo.count_logged_in_since(datetime.now(UTC) - timedelta(minutes=1)) == 1
    assert await repo.get_by_max_id(10) is not None
    assert await repo.get_by_max_id(11) is None
    assert same.display_name == "B"


async def test_refresh_token_lifecycle(session: AsyncSession) -> None:
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(max_user_id=1, first_name="A"), touch_login=False, now=datetime.now(UTC)
    )
    repo = RefreshTokenRepository(session)
    now = datetime.now(UTC)
    live = await repo.create(
        user_id=user.id, token_hash="h1", family_id="f1", expires_at=now + timedelta(days=1)
    )
    await repo.create(
        user_id=user.id, token_hash="h2", family_id="f1", expires_at=now - timedelta(days=1)
    )
    assert (await repo.get_by_hash("h1")) is live
    assert (await repo.get_by_hash("h1")).expires_at.tzinfo is not None

    await repo.mark_rotated(live, replaced_by_hash="h3", now=now)
    assert live.revoked_at == now and live.replaced_by_hash == "h3"
    assert await repo.delete_expired_for_user(user.id, before=now) == 1
    assert await repo.get_by_hash("h2") is None

    await repo.create(
        user_id=user.id, token_hash="h4", family_id="f2", expires_at=now + timedelta(days=1)
    )
    assert await repo.revoke_all_for_user(user.id, now=now) == 1
    assert await repo.revoke_family("f2", now=now) == 0


async def test_upsert_survives_concurrent_insert(session: AsyncSession, monkeypatch) -> None:
    """Гонка двух входов: чтение вернуло None, а строка уже появилась к моменту вставки."""
    repo = UserRepository(session)
    existing = await repo.upsert_from_max(
        UserUpsert(max_user_id=77, first_name="First"), touch_login=False, now=datetime.now(UTC)
    )
    await session.flush()

    real_get = UserRepository.get_by_max_id
    calls = {"n": 0}

    async def racing_get(self, max_user_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # первый запрос ещё не видит строку соседа
        return await real_get(self, max_user_id)

    monkeypatch.setattr(UserRepository, "get_by_max_id", racing_get)
    user = await repo.upsert_from_max(
        UserUpsert(max_user_id=77, first_name="Second"), touch_login=True, now=datetime.now(UTC)
    )
    assert user.id == existing.id and user.first_name == "Second"
    assert await repo.count() == 1


async def test_file_record_survives_concurrent_first_render(session: AsyncSession) -> None:
    """Две сборки сразу: обе не нашли запись и вставляют — вторая обновляет первую."""
    from sqlalchemy import func, select

    from core.db.models import DocumentFile
    from core.db.repositories import DocumentFileRepository

    repo = DocumentFileRepository(session)
    first = {"filename": "a.docx", "path": "1/a", "size": 1, "sha256": "a", "source_sha256": "a"}
    await repo.upsert(document_id=1, fmt="docx", **first)
    real_get = repo.get
    looked = 0

    async def not_yet_visible(document_id: int, fmt: str) -> DocumentFile | None:
        nonlocal looked
        looked += 1
        return None if looked == 1 else await real_get(document_id, fmt)

    repo.get = not_yet_visible  # type: ignore[method-assign]
    second = {"filename": "b.docx", "path": "1/b", "size": 2, "sha256": "b", "source_sha256": "b"}
    record = await repo.upsert(document_id=1, fmt="docx", **second)

    assert record.sha256 == "b"
    count = select(func.count()).select_from(DocumentFile)
    assert (await session.execute(count)).scalar_one() == 1
