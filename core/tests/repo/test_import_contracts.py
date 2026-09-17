"""Архитектурные контракты Python (pyproject [tool.importlinter]) и TS (.dependency-cruiser.cjs)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CORE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = CORE_ROOT.parent


def _run(cmd: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def test_python_layer_contracts() -> None:
    # Бинарь берётся из окружения, где запущен pytest: на хосте это core/.venv, в
    # тестовом образе deploy.sh — /opt/venv (хостовый .venv там смонтирован, но чужой).
    exe = Path(sys.executable).parent / "lint-imports"
    if not exe.exists():
        pytest.skip("import-linter не установлен (uv sync)")
    # Без кеша: в тестовом образе репозиторий смонтирован read-only.
    result = _run([str(exe), "--no-cache"], cwd=CORE_ROOT)
    assert result.returncode == 0, (
        f"контракты слоёв core нарушены:\n{result.stdout}\n{result.stderr}"
    )


def test_ts_dependency_contracts() -> None:
    binary = REPO_ROOT / "node_modules" / ".bin" / "depcruise"
    if not binary.exists() or shutil.which("node") is None:
        # В тестовом образе core нет Node: TS-контракты проверяет `./maxapp check` на хосте.
        pytest.skip("dependency-cruiser или node недоступны")
    result = _run(
        [str(binary), "bot/src", "web/src", "--config", ".dependency-cruiser.cjs"], cwd=REPO_ROOT
    )
    assert result.returncode == 0, (
        f"контракты .dependency-cruiser.cjs нарушены:\n{result.stdout}\n{result.stderr}"
    )


def test_no_leftovers_of_the_old_layout() -> None:
    """Корневые пакеты старой раскладки (api/, services/, shared/, db/, jobs/) и их
    кеши возвращались после удаления: репозиторий лежит в каталоге, который
    синхронизирует iCloud. Замок ловит это раньше, чем pre-commit подхватит мусор."""
    stale = [
        name
        for name in (
            "api",
            "services",
            "shared",
            "db",
            "jobs",
            "nginx",
            "scripts",
            "tests",
            ".venv",
            ".importlinter",
            ".npmrc",
        )
        if (REPO_ROOT / name).exists()
    ]
    stale += [
        str(p.relative_to(REPO_ROOT))
        for p in (
            CORE_ROOT / "src" / "core" / "jobs",
            CORE_ROOT / "src" / "core" / "config" / "jobs.py",
            CORE_ROOT / "tests" / "jobs",
            CORE_ROOT / "tests" / "shared",
            REPO_ROOT / "gateway" / "dev.conf",
        )
        if p.exists()
    ]
    assert not stale, (
        f"в корне остатки старой раскладки: {stale} (rm -rf и вынести репозиторий из iCloud)"
    )
