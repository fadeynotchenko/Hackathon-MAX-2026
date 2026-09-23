"""Замки на инфраструктуру: compose, nginx, Dockerfile, каталог джоб.

Файлы читаются как текст: тест быстрый и не требует docker.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = CORE_ROOT.parent


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prod() -> str:
    return _read("docker-compose.prod.yml")


@pytest.fixture(scope="module")
def dev() -> str:
    return _read("compose.yaml")


@pytest.fixture(scope="module")
def nginx_template() -> str:
    return _read("gateway/templates/default.conf.template")


def _services(compose: str) -> set[str]:
    block = compose.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    return set(re.findall(r"^  ([a-z_]+):\n", block, re.M))


def test_stacks_contain_exactly_the_expected_services(prod: str, dev: str) -> None:
    """Без лишних контейнеров: миграции и потребитель событий живут внутри api."""
    assert _services(prod) == {"db", "redis", "api", "bot", "gateway", "db_backup"}
    assert _services(dev) == {"db", "redis", "deps", "api", "bot", "web"}


def test_api_waits_for_db_and_redis(prod: str, dev: str) -> None:
    for compose in (prod, dev):
        api_block = compose.split("\n  api:\n", 1)[1].split("\n  bot:\n", 1)[0]
        assert "db:\n        condition: service_healthy" in api_block
        assert "redis:\n        condition: service_healthy" in api_block


def test_migrations_are_serialized_by_advisory_lock() -> None:
    """api применяет миграции при старте; несколько воркеров не должны гоняться за alembic_version."""
    env = (CORE_ROOT / "src" / "core" / "db" / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in env
    main = (CORE_ROOT / "src" / "core" / "api" / "main.py").read_text(encoding="utf-8")
    assert "await upgrade_to_head()" in main


def test_prod_hardening(prod: str) -> None:
    assert "read_only: true" in prod and "no-new-privileges:true" in prod
    assert prod.count("cap_drop: [ALL]") >= 3
    assert "--requirepass" in prod, "Redis в проде только с паролем"
    assert "ENV: production" in prod


def test_prod_postgres_tuning(prod: str) -> None:
    assert re.search(r"max_connections=(\d+)", prod)
    assert re.search(r"idle_in_transaction_session_timeout=(\d+)", prod)


def test_nginx_rate_limits_and_429(nginx_template: str) -> None:
    assert re.search(r"zone=api_general:\d+m\s+rate=\d+r/s", nginx_template)
    assert re.search(r"zone=api_auth:\d+m\s+rate=\d+r/[sm]", nginx_template)
    assert "limit_req_status 429" in nginx_template and "limit_conn_status 429" in nginx_template
    assert "location = /api/v1/auth/max" in nginx_template, "вход по initData — своя зона лимитов"


def test_nginx_routes_webhook_and_api(nginx_template: str) -> None:
    assert "location = ${BOT_WEBHOOK_PATH}" in nginx_template
    assert "proxy_pass $bot_upstream" in nginx_template
    assert "proxy_pass $api_upstream" in nginx_template
    assert "resolver 127.0.0.11" in nginx_template, "апстримы резолвятся при запросе"
    assert "X-Request-ID" in _read("gateway/snippets/proxy_common.conf")


def test_csp_allows_max_bridge_and_frames() -> None:
    csp = re.search(
        r'Content-Security-Policy\s+"([^"]+)"', _read("gateway/snippets/security_headers.conf")
    )
    assert csp, "CSP не найдена"
    value = csp.group(1)
    assert "script-src 'self' https://st.max.ru" in value, "мост MAX грузится с st.max.ru"
    assert "frame-ancestors" in value and "max.ru" in value, (
        "веб-клиент MAX открывает мини-апп во фрейме"
    )
    assert "add_header X-Frame-Options" not in _read("gateway/snippets/security_headers.conf"), (
        "конфликтует с frame-ancestors"
    )


def test_dockerfile_runs_as_non_root() -> None:
    assert "USER app" in _read("core/Dockerfile")
    assert "USER node" in _read("bot/Dockerfile")
    assert "uv sync --frozen" in _read("core/Dockerfile")


def test_python_entrypoints_use_module_form(prod: str, dev: str) -> None:
    """Только `python -m` и `uvicorn api.main:app`: запуск файлом кладёт его каталог
    в sys.path и даёт модулям второе имя (см. эталон Tihost, «один пакет — одно имя»)."""
    for compose in (prod, dev):
        assert not re.search(r"python\s+[a-z_/]+\.py", compose)
    assert 'CMD ["uvicorn", "core.api.main:app"' in _read("core/Dockerfile")


def test_bot_image_trusts_russian_root_ca() -> None:
    """platform-api2.max.ru подписан корнем Минцифры; без него бот не стартует."""
    assert (REPO_ROOT / "bot" / "certs" / "russian_trusted_root_ca.pem").exists()
    dockerfile = _read("bot/Dockerfile")
    assert "NODE_EXTRA_CA_CERTS" in dockerfile and "russian_trusted_root_ca.pem" in dockerfile
    assert "NODE_EXTRA_CA_CERTS" in _read("compose.yaml")
