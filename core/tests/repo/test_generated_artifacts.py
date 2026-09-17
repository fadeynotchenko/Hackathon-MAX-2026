"""Сгенерированные артефакты совпадают с источником правды.

.env.example ← core.config.env_spec, contracts/openapi.json ← core.api,
contracts/events.schema.json ← core.events.contracts. Дрейф ловится здесь,
а не «когда заметят».
"""

from __future__ import annotations

from pathlib import Path

from core.scripts import export_event_schemas, export_openapi, gen_env_example

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_env_example_current() -> None:
    assert gen_env_example.ENV_EXAMPLE_PATH.read_text(encoding="utf-8") == gen_env_example.render()


def test_openapi_current() -> None:
    assert export_openapi.OPENAPI_PATH.read_text(encoding="utf-8") == export_openapi.render(), (
        "contracts/openapi.json устарел: uv run python -m core.scripts.export_openapi && pnpm --filter @maxapp/web gen:api"
    )


def test_event_schema_current() -> None:
    assert (
        export_event_schemas.SCHEMA_PATH.read_text(encoding="utf-8")
        == export_event_schemas.render()
    ), "bot/src/events/schema.json устарел: uv run python -m scripts.export_event_schemas"


def test_ts_api_types_not_older_than_openapi() -> None:
    """schema.d.ts генерируется из openapi.json; отставание означает забытый gen:api."""
    schema = REPO_ROOT / "web" / "src" / "api" / "schema.d.ts"
    assert schema.exists(), "нет web/src/api/schema.d.ts: pnpm --filter @maxapp/web gen:api"
    content = schema.read_text(encoding="utf-8")
    for op in (
        "login_max",
        "refresh_session",
        "logout",
        "get_me",
        "admin_stats",
        "admin_notify",
        "health",
    ):
        assert op in content, f"operation_id {op} нет в schema.d.ts — перегенерируйте типы"
