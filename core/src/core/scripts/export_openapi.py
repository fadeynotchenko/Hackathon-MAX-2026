"""Экспорт OpenAPI-схемы API в contracts/openapi.json.

    uv run python -m core.scripts.export_openapi          # перезаписать
    uv run python -m core.scripts.export_openapi --check  # сверить (tests/repo)

contracts/ — единственное, что сервисы разделяют. Из этого файла
``pnpm --filter @maxapp/web gen:api`` генерирует TypeScript-типы
(web/src/api/schema.d.ts): контракт между core и web проверяет компилятор.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = CORE_ROOT.parent
OPENAPI_PATH = REPO_ROOT / "contracts" / "openapi.json"


def render() -> str:
    from core.api.main import create_app
    from core.config.app_config import AppConfig

    # Схема не зависит от окружения: собираем приложение с dev-конфигом без lifespan.
    config = AppConfig(
        env="dev",
        log_level="INFO",
        public_base_url="",
        admin_max_ids=frozenset(),
        cors_allow_origins=(),
        request_timeout_seconds=30,
        dev_login_enabled=True,
    )
    app = create_app(app_config=config, lifespan_factory=None, request_timeout_seconds=30)
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    rendered = render()
    if "--check" in argv:
        current = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else ""
        if current != rendered:
            print(
                "openapi.json устарел: python -m scripts.export_openapi && pnpm gen:api",
                file=sys.stderr,
            )
            return 1
        print("openapi.json актуален")
        return 0
    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(rendered, encoding="utf-8")
    print(f"записан {OPENAPI_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
