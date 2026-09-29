"""DATA-API.yaml проходит на текущем коде: сценарий технической проверки жюри.

Валидатор организаторов сверяет только формат файла. Здесь те же запросы идут в
приложение по порядку — переменные из ``extract``, роль ``user`` с токеном
учётки проверяющих, затем ``cleanup`` — и каждый ответ сравнивается с
``expected``. Поле, которого больше нет в шаблоне (так было с ``item`` и
``total`` после перехода счёта на позиции), валит прогон здесь, а не у жюри.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.usecases.auth import issue_reviewer_access
from core.usecases.auth.config import AuthConfig
from core.usecases.documents import ensure_builtin_templates

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC = yaml.safe_load((REPO_ROOT / "DATA-API.yaml").read_text(encoding="utf-8"))
TEST_DATA = json.loads((REPO_ROOT / "test-data.json").read_text(encoding="utf-8"))

_VARIABLE = re.compile(r"\$\{(\w+)\}")
_JSONPATH_STEP = re.compile(r"\.(\w+)|\[(\d+)\]")
# Ключи bodySchema, которые проверка понимает: незнакомый ключ — ошибка теста,
# а не молча пропущенное условие.
_SCHEMA_KEYS = frozenset({"type", "required", "properties", "const"})
_JSON_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool}


def _substitute(value: Any, variables: dict[str, Any]) -> Any:
    """Подстановка ``${name}`` строкой: так поступит любой шаблонизатор, и API
    обязан принять id строкой так же, как числом."""
    if isinstance(value, str):
        return _VARIABLE.sub(lambda match: str(variables[match.group(1)]), value)
    if isinstance(value, dict):
        return {key: _substitute(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, variables) for item in value]
    return value


def _extract(body: Any, path: str) -> Any:
    """JSONPath из ``extract`` в объёме DATA-API: ``$.id``, ``$[0].id``."""
    steps = list(_JSONPATH_STEP.finditer(path[1:]))
    assert path.startswith("$") and "".join(m.group(0) for m in steps) == path[1:], path
    for match in steps:
        key, index = match.groups()
        body = body[key] if key is not None else body[int(index)]
    return body


def _check_schema(schema: dict[str, Any], value: Any, where: str) -> None:
    unknown = set(schema) - _SCHEMA_KEYS
    assert not unknown, f"{where}: bodySchema с {unknown} тест не проверяет"
    if "type" in schema:
        assert isinstance(value, _JSON_TYPES[schema["type"]]), f"{where}: не {schema['type']}"
    if "const" in schema:
        assert value == schema["const"], f"{where}: {value!r} вместо {schema['const']!r}"
    for key in schema.get("required", ()):
        assert key in value, f"{where}: нет поля {key}"
    for key, sub in schema.get("properties", {}).items():
        if key in value:
            _check_schema(sub, value[key], f"{where}.{key}")


def _check_expected(step: dict[str, Any], response: Response) -> Any:
    expected = step.get("expected", {})
    where = step["id"]
    assert response.status_code in expected.get("statusCodes", [200]), (
        f"{where}: {response.status_code} {response.text[:500]}"
    )
    content_type = response.headers.get("content-type", "")
    if "contentType" in expected:
        assert content_type.startswith(expected["contentType"]), f"{where}: {content_type}"
    body = response.json() if content_type.startswith("application/json") else None
    for field in expected.get("requiredFields", ()):
        assert isinstance(body, dict) and field in body, f"{where}: нет поля {field}"
    if "bodySchema" in expected:
        _check_schema(expected["bodySchema"], body, where)
    return body


async def _call(
    client: AsyncClient, step: dict[str, Any], variables: dict[str, Any], token: str
) -> Response:
    request = _substitute(step.get("request", {}), variables)
    path = step["path"]
    for name, value in request.get("path", {}).items():
        path = path.replace("{" + name + "}", str(value))
    assert "{" not in path, f"{step['id']}: не подставлен параметр пути в {path}"
    headers = {**SPEC["api"].get("defaultHeaders", {}), **request.get("headers", {})}
    if step["role"] != "public":
        headers["Authorization"] = f"Bearer {token}"
    return await client.request(
        step["method"],
        path,
        params=request.get("query"),
        headers=headers,
        content=json.dumps(request["body"], ensure_ascii=False) if "body" in request else None,
    )


@pytest.fixture
async def reviewer_token(session: AsyncSession, auth_config: AuthConfig) -> str:
    """Тот же токен, что оператор выпускает жюри (core.scripts.issue_reviewer_token)."""
    await ensure_builtin_templates(session)
    access = await issue_reviewer_access(session, cfg=auth_config, days=14)
    await session.commit()
    return access.access_token


async def _run_checks(client: AsyncClient, token: str) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    bodies: dict[str, Any] = {}
    for step in SPEC["checks"]:
        missing = set(step.get("dependsOn", ())) - set(bodies)
        assert not missing, f"{step['id']} зависит от ещё не выполненных {missing}"
        response = await _call(client, step, variables, token)
        bodies[step["id"]] = _check_expected(step, response)
        for name, path in step.get("extract", {}).items():
            variables[name] = _extract(bodies[step["id"]], path)
    for step in SPEC.get("cleanup", ()):
        _check_expected(step, await _call(client, step, variables, token))
    return bodies


async def test_every_check_passes_and_cleanup_removes_what_it_created(
    client: AsyncClient, reviewer_token: str
) -> None:
    bodies = await _run_checks(client, reviewer_token)

    filled = bodies["fill-document"]
    assert filled["errors"] == [], filled["errors"]
    preview = filled["preview"].replace("\xa0", " ")
    for text in TEST_DATA["invoice"]["expected"].values():
        assert text in preview, f"в предпросмотре нет «{text}»"

    headers = {"Authorization": f"Bearer {reviewer_token}"}
    for listing in ("/api/v1/documents", "/api/v1/counterparties", "/api/v1/organizations"):
        response = await client.get(listing, headers=headers)
        assert response.json() == [], f"{listing}: cleanup оставил данные проверки"


async def test_scenario_is_repeatable(client: AsyncClient, reviewer_token: str) -> None:
    """Жюри может прогнать сценарий повторно той же учёткой: второй проход
    после cleanup проходит так же, как первый."""
    await _run_checks(client, reviewer_token)
    await _run_checks(client, reviewer_token)


def test_request_bodies_match_test_data_file() -> None:
    steps = {step["id"]: step for step in [*SPEC["checks"], *SPEC.get("cleanup", ())]}
    assert steps["create-organization"]["request"]["body"] == TEST_DATA["organization"]["body"]
    assert steps["create-counterparty"]["request"]["body"] == TEST_DATA["counterparty"]["body"]
    sent = steps["fill-document"]["request"]["body"]["values"]
    invoice = TEST_DATA["invoice"]["values"]
    assert set(sent) == set(invoice)
    for key, value in invoice.items():
        raw = sent[key]["value"]
        assert (json.loads(raw) if key == "items" else raw) == value, key
    template_step = steps["invoice-template"]
    assert template_step["request"]["query"]["slug"] == TEST_DATA["invoice"]["template_slug"]


def test_no_secrets_in_data_api() -> None:
    """Токен проверяющего передаётся отдельным каналом, в файле его быть не может."""
    text = (REPO_ROOT / "DATA-API.yaml").read_text(encoding="utf-8")
    assert "Authorization" not in text.split("checks:", 1)[1]
    assert not re.search(r"eyJ[\w-]{10,}\.", text), "в DATA-API.yaml похоже на JWT"
