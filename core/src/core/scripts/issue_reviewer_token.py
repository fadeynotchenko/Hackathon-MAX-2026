"""Долгий токен учётки проверяющих для HTTP-проверок (DATA-API.yaml, роль user).

    uv run python -m core.scripts.issue_reviewer_token --days 14
    uv run python -m core.scripts.issue_reviewer_token --revoke

На проде — внутри контейнера api, где уже есть окружение и доступ к базе:

    docker compose -f docker-compose.prod.yml exec api python -m core.scripts.issue_reviewer_token --days 14

Печатает токен для заголовка ``Authorization: Bearer <токен>``. Учётка отдельная
(по умолчанию выдуманный MAX-id): документы проверяющих не смешиваются с
настоящими. ``--revoke`` удаляет учётку вместе с её данными — токен перестаёт
работать сразу.
"""

from __future__ import annotations

import argparse
import asyncio

from core.db import close_db, get_session, init_db
from core.db.config import DatabaseConfig
from core.usecases.auth import (
    MAX_REVIEWER_DAYS,
    REVIEWER_MAX_USER_ID,
    get_auth_config,
    issue_reviewer_access,
    revoke_reviewer_access,
)


async def _run(args: argparse.Namespace) -> str:
    await init_db(DatabaseConfig.from_env())
    try:
        async with get_session() as session:
            if args.revoke:
                revoked = await revoke_reviewer_access(session, max_user_id=args.max_user_id)
                return "учётка удалена, токены отозваны" if revoked else "учётки нет"
            access = await issue_reviewer_access(
                session,
                cfg=get_auth_config(),
                days=args.days,
                max_user_id=args.max_user_id,
                first_name=args.name,
            )
        return (
            f"MAX-id {access.max_user_id}, действует до {access.expires_at:%Y-%m-%d %H:%M} UTC\n"
            f"Authorization: Bearer {access.access_token}"
        )
    finally:
        await close_db()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--days", type=int, default=14, help=f"1–{MAX_REVIEWER_DAYS}")
    parser.add_argument("--max-user-id", type=int, default=REVIEWER_MAX_USER_ID)
    parser.add_argument("--name", default="Проверяющий")
    parser.add_argument("--revoke", action="store_true", help="удалить учётку и её токены")
    args = parser.parse_args()
    if not 1 <= args.days <= MAX_REVIEWER_DAYS:
        parser.error(f"--days: от 1 до {MAX_REVIEWER_DAYS}")
    print(asyncio.run(_run(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
