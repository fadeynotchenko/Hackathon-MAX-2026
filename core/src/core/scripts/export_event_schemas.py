"""Экспорт JSON Schema контрактов событий в contracts/events.schema.json.

    uv run python -m core.scripts.export_event_schemas          # перезаписать
    uv run python -m core.scripts.export_event_schemas --check  # сверить (tests/repo)

Источник правды — core.events.contracts. Бот держит zod-схемы руками
(bot/src/events/codec.ts), а vitest сверяет их с этим файлом: набор событий,
имена и обязательность полей, версия конверта. Дрейф ловится тестом, а не в проде.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core.events.contracts import ENVELOPE_VERSION, EVENT_PAYLOADS

CORE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = CORE_ROOT.parent
SCHEMA_PATH = REPO_ROOT / "contracts" / "events.schema.json"


def render() -> str:
    document = {
        "$comment": "Сгенерировано core/src/core/scripts/export_event_schemas.py из core.events.contracts. Руками не править.",
        "envelope_version": ENVELOPE_VERSION,
        "envelope": {
            "type": "object",
            "required": ["id", "v", "type", "payload", "ts", "source"],
            "properties": {
                "id": {"type": "string", "description": "UUID события (hex, 32 символа)"},
                "v": {
                    "type": "string",
                    "description": "Версия конверта, число в строке (поля стрима — строки)",
                },
                "type": {"type": "string"},
                "payload": {"type": "string", "description": "JSON-объект, форма — events[type]"},
                "ts": {"type": "string", "format": "date-time"},
                "source": {"type": "string"},
            },
        },
        "events": {name: model.model_json_schema() for name, model in EVENT_PAYLOADS.items()},
    }
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    rendered = render()
    if "--check" in argv:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current != rendered:
            print(
                "bot/src/events/schema.json устарел: python -m scripts.export_event_schemas",
                file=sys.stderr,
            )
            return 1
        print("schema.json актуален")
        return 0
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(rendered, encoding="utf-8")
    print(f"записан {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
