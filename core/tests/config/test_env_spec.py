"""Реестр env: целостность, синхронность с .env.example, анти-дрейф в коде и compose."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from core.config import env_spec
from core.config.env_spec import (
    ALL_LAYERS,
    ENV_SPEC,
    GROUP_ORDER,
    VALID_TYPES,
    EnvValidationError,
    validate_env,
    validate_env_or_raise,
)
from core.scripts.gen_env_example import ENV_EXAMPLE_PATH, render

CORE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = CORE_ROOT.parent
NAMES = {v.name for v in ENV_SPEC}

# Где разрешено читать os.environ напрямую. Всё остальное — через core.config.env.
DIRECT_ENV_ALLOWED = {Path("src/core/config/env.py"), Path("tests/conftest.py")}
SCANNED_DIRS = ("src/core", "tests")
ENV_HELPERS = {
    "get_env",
    "get_env_int",
    "get_env_bool",
    "get_env_list",
    "get_env_int_list",
    "default_for",
    "spec_for",
}


def _python_files():
    for directory in SCANNED_DIRS:
        for path in (CORE_ROOT / directory).rglob("*.py"):
            if "__pycache__" in path.parts or re.search(r" \d{1,2}$", path.stem):
                continue
            yield path


def test_registry_integrity() -> None:
    seen: set[str] = set()
    for var in ENV_SPEC:
        assert var.name not in seen, f"дубль {var.name}"
        seen.add(var.name)
        assert re.fullmatch(r"[A-Z][A-Z0-9_]+", var.name), var.name
        assert var.type in VALID_TYPES, var.name
        assert var.group in GROUP_ORDER, f"{var.name}: группа {var.group} не в GROUP_ORDER"
        assert var.description.strip(), var.name
        assert var.owner.strip(), f"{var.name}: укажи, кто читает переменную"
        assert var.required_for <= ALL_LAYERS, var.name
        if var.secret:
            assert var.default is None, f"{var.name}: у секрета не бывает дефолта"


def test_env_example_is_in_sync() -> None:
    assert ENV_EXAMPLE_PATH.exists(), (
        "нет .env.example: uv run python -m core.scripts.gen_env_example"
    )
    assert ENV_EXAMPLE_PATH.read_text(encoding="utf-8") == render(), (
        ".env.example разошёлся с реестром: uv run python -m core.scripts.gen_env_example"
    )


def test_no_direct_os_environ_outside_env_module() -> None:
    offenders: list[str] = []
    for path in _python_files():
        rel = path.relative_to(CORE_ROOT)
        if rel in DIRECT_ENV_ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in {"getenv", "environ"}
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
            ):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, "os.environ вне core/config/env.py: " + ", ".join(offenders)


def test_every_env_name_read_in_code_is_registered() -> None:
    unknown: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in ENV_HELPERS or not node.args:
                continue
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value not in NAMES
            ):
                unknown.append(f"{path.relative_to(CORE_ROOT)}:{node.lineno} {first.value}")
    assert not unknown, "переменные без записи в env_spec: " + ", ".join(unknown)


def test_compose_and_deploy_variables_are_registered() -> None:
    # ${NAME} и ${NAME:-default} в compose/nginx/deploy.sh; $$ — экранирование shell внутри compose.
    pattern = re.compile(r"(?<!\$)\$\{([A-Z][A-Z0-9_]+)(?::-[^}]*)?\}")
    files = (
        list(REPO_ROOT.glob("docker-compose*.yml"))
        + list((REPO_ROOT / "gateway").rglob("*.template"))
        + [REPO_ROOT / "deploy.sh"]
    )
    unknown: set[str] = set()
    for file in files:
        if not file.exists():
            continue
        for match in pattern.finditer(file.read_text(encoding="utf-8")):
            name = match.group(1)
            # POSTGRES_* — переменные образа postgres, им значения даёт compose из DB_*.
            if name not in NAMES and not name.startswith(("POSTGRES_", "PG")):
                unknown.add(f"{file.name}:{name}")
    assert not unknown, "переменные compose без записи в env_spec: " + ", ".join(sorted(unknown))


def test_bot_config_variables_are_registered() -> None:
    config_ts = REPO_ROOT / "bot" / "src" / "config.ts"
    if not config_ts.exists():
        pytest.skip("bot/src/config.ts ещё не написан")
    names = set(
        re.findall(r"^\s+([A-Z][A-Z0-9_]+):\s", config_ts.read_text(encoding="utf-8"), re.M)
    )
    assert names, "в bot/src/config.ts не найдено объявлений переменных"
    assert names <= NAMES, f"переменные бота без записи в env_spec: {sorted(names - NAMES)}"


def test_validate_env_reports_missing_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("DB_PORT", "not-a-number")
    report = validate_env("api")
    assert not report.ok
    assert any(v.name == "JWT_SECRET" for v in report.missing)
    assert any("DB_PORT" in msg for msg in report.invalid)
    assert "JWT_SECRET" in report.format()
    with pytest.raises(EnvValidationError):
        validate_env_or_raise("api")


def test_validate_env_ok_for_test_environment() -> None:
    report = validate_env_or_raise("api")
    assert report.ok and report.checked > 0
    assert "всё на месте" in report.format()


def test_unknown_layer_rejected() -> None:
    with pytest.raises(ValueError):
        validate_env("web")


def test_group_titles_cover_all_groups() -> None:
    assert set(GROUP_ORDER) <= set(env_spec.GROUP_TITLES)


def test_dev_only_values_are_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "dev-only-jwt-secret-change-in-production-0123456789")
    report = validate_env("api")
    assert any("JWT_SECRET" in msg and "dev-плейсхолдер" in msg for msg in report.invalid)
    monkeypatch.setenv("ENV", "dev")
    assert not any("JWT_SECRET" in msg for msg in validate_env("api").invalid)


def test_env_example_boots_a_dev_stack() -> None:
    """Плейсхолдеры из .env.example удовлетворяют валидатору вне production."""
    from core.usecases.auth.config import AuthConfig

    values = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    AuthConfig(
        bot_token=values["MAX_BOT_TOKEN"],
        jwt_secret=values["JWT_SECRET"],
        access_ttl_seconds=900,
        refresh_ttl_seconds=2592000,
        init_data_max_age_seconds=86400,
    ).validate()
    assert values["DB_PASSWORD"] and values["REDIS_PASSWORD"]


def test_dev_login_flag_is_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DEV_LOGIN_ENABLED", "true")
    assert any("DEV_LOGIN_ENABLED" in msg for msg in validate_env("api").invalid)


def test_explicitly_empty_log_dir_disables_file_log(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.config.env import get_env_or_default

    monkeypatch.setenv("LOG_DIR", "")
    assert get_env_or_default("LOG_DIR", "app_logs") == ""
    monkeypatch.delenv("LOG_DIR")
    assert get_env_or_default("LOG_DIR", "app_logs") == "app_logs"


def test_model_gives_up_before_the_request_does() -> None:
    by_name = {var.name: var for var in ENV_SPEC}
    model = int(by_name["GIGACHAT_TIMEOUT_SECONDS"].default or 0)
    request = int(by_name["API_REQUEST_TIMEOUT_SECONDS"].default or 0)
    assert 0 < model < request, "зависшая модель должна давать 503 помощника, а не общий 504"
