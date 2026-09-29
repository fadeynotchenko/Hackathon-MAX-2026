"""Экспорт тестовых данных технической проверки в корневой test-data.json.

    uv run python -m core.scripts.export_test_data          # перезаписать
    uv run python -m core.scripts.export_test_data --check  # сверить (tests/repo)

Для решений со своим API хакатон требует тестовые данные файлом. Реквизиты
берутся из ``core.usecases.documents.demo`` — того же набора, что подставляет
кнопка «Тестовые реквизиты»: вымышленные ИНН, ОГРН и счета с верными
контрольными разрядами. Тела запросов в DATA-API.yaml обязаны совпадать с этим
файлом (tests/api/test_data_api.py), поэтому проверяющий видит одни и те же
значения в файле, в сценарии и в ответах API.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core.usecases.documents.demo import DEMO_CLIENT, DEMO_SELLER

CORE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = CORE_ROOT.parent
TEST_DATA_PATH = REPO_ROOT / "test-data.json"

INVOICE = {
    "template_slug": "invoice",
    "values": {
        "number": "1",
        "date": "24.09.2026",
        "items": [
            {
                "name": "Подготовка пакета документов",
                "quantity": "1",
                "unit": "усл.",
                "price": "100000",
            },
            {
                "name": "Консультация юриста",
                "quantity": "2",
                "unit": "ч",
                "price": "10000",
            },
        ],
    },
    "expected": {"total": "120 000,00", "total_in_words": "Сто двадцать тысяч рублей 00 копеек"},
}


def _card(requisites: dict[str, str]) -> dict[str, object]:
    """Тело POST /organizations и /counterparties: название отдельно от реквизитов."""
    values = {key: value for key, value in requisites.items() if key != "name"}
    return {"name": requisites["name"], "values": values}


def build() -> dict[str, object]:
    return {
        "about": (
            "Тестовые данные для проверки API и мини-приложения. Реквизиты вымышленные, "
            "но с верными контрольными суммами ИНН, ОГРН, КПП и ключом счёта по БИК; "
            "БИК и корр. счета — настоящих банков, почта — в домене .example. "
            "Те же значения стоят в DATA-API.yaml и в примерах README."
        ),
        "organization": {
            "endpoint": "POST /api/v1/organizations",
            "body": _card(DEMO_SELLER),
        },
        "counterparty": {
            "endpoint": "POST /api/v1/counterparties",
            "body": _card(DEMO_CLIENT),
        },
        "invoice": {
            "endpoint": "PATCH /api/v1/documents/{document_id}/fields",
            **INVOICE,
        },
    }


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    rendered = render()
    if "--check" in argv:
        current = TEST_DATA_PATH.read_text(encoding="utf-8") if TEST_DATA_PATH.exists() else ""
        if current != rendered:
            print(
                "test-data.json устарел: uv run python -m core.scripts.export_test_data",
                file=sys.stderr,
            )
            return 1
        print("test-data.json актуален")
        return 0
    TEST_DATA_PATH.write_text(rendered, encoding="utf-8")
    print(f"записан {TEST_DATA_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
