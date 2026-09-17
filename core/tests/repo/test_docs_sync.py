"""Документация обязана сходиться с кодом: замок на устаревшие README/AGENTS/docs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.config.env_spec import ENV_SPEC

CORE_ROOT = Path(__file__).resolve().parents[2]
ROOT = CORE_ROOT.parent
DOCS = [
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/ARCHITECTURE.md",
    "docs/DEPLOY.md",
    "docs/LOGGING.md",
    "docs/MAX_PLATFORM.md",
]


def _read(path: str) -> str:
    file = ROOT / path
    assert file.exists(), f"нет {path}"
    return file.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", DOCS)
def test_docs_exist_and_not_empty(path: str) -> None:
    assert len(_read(path).strip()) > 200, f"{path} пуст или заглушка"


def test_claude_md_includes_agents_md() -> None:
    assert "@AGENTS.md" in _read("CLAUDE.md"), (
        "CLAUDE.md подключает AGENTS.md через @-импорт, а не копирует его"
    )


def test_agents_md_mentions_every_service_and_core_package() -> None:
    text = _read("AGENTS.md")
    for service in ("core/", "bot/", "web/", "gateway/", "contracts/", "docs/"):
        assert f"`{service}`" in text, f"AGENTS.md не описывает {service}"
    core_packages = sorted(
        p.name
        for p in (CORE_ROOT / "src" / "core").iterdir()
        if p.is_dir() and not p.name.startswith("__")
    )
    for package in core_packages:
        assert f"`{package}/`" in text, f"AGENTS.md не описывает core-пакет {package}/"


def test_core_build_context_is_isolated() -> None:
    """core собирается из своего каталога: образ физически не видит bot/ и web/.

    Это и есть граница сервиса на уровне сборки; импорты держат import-linter
    (root_package = core) и dependency-cruiser (bot/web ⊅ core).
    """
    for compose in ("docker-compose.dev.yml", "docker-compose.prod.yml"):
        text = _read(compose)
        assert "context: ./core" in text, f"{compose}: core должен собираться из ./core"
    dockerfile = (CORE_ROOT / "Dockerfile").read_text(encoding="utf-8")
    for line in dockerfile.splitlines():
        if line.startswith("COPY ") and "--from=" not in line:
            source = line.split()[1]
            assert not source.startswith(("../", "/", "bot", "web", "gateway")), line


def test_architecture_doc_lists_core_layers() -> None:
    pyproject = (CORE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    layers = re.findall(
        r'^\s+"(core\.[a-z| .]+)",$', pyproject.split("[[tool.importlinter.contracts]]", 1)[1], re.M
    )
    assert layers, "в pyproject нет layers-контракта"
    text = _read("docs/ARCHITECTURE.md")
    for layer in layers:
        for module in layer.split("|"):
            name = module.strip().removeprefix("core.")
            assert f"`{name}`" in text or f"`{name}/`" in text, (
                f"слой {name} не описан в docs/ARCHITECTURE.md"
            )


def test_readme_run_commands_match_files() -> None:
    text = _read("README.md")
    for needle in (
        "docker-compose.dev.yml",
        "docker-compose.prod.yml",
        "./maxapp",
        "./deploy.sh",
        ".env.example",
    ):
        assert needle in text, f"README не упоминает {needle}"


def test_env_docs_reference_registry() -> None:
    text = _read("docs/DEPLOY.md")
    required = sorted(v.name for v in ENV_SPEC if v.required_for)
    for name in required:
        assert name in text, f"обязательная переменная {name} не упомянута в docs/DEPLOY.md"


def test_no_ai_marker_rule_is_documented() -> None:
    text = _read("AGENTS.md")
    assert "ai_markers.txt" in text, (
        "правило про комментарии без маркеров генерации должно ссылаться на список"
    )
