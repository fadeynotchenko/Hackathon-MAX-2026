"""Замок на «слоп»: маркеры сгенерированного текста в коде и документах.

Список шаблонов — tests/meta/ai_markers.txt (по одному регулярному выражению
в строке). Сканируются исходники и документация; артефакты генерации
(openapi.json, schema.d.ts, lock-файлы) и каталоги зависимостей пропускаются.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MARKERS_FILE = Path(__file__).with_name("ai_markers.txt")

SCANNED_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".md",
    ".yml",
    ".yaml",
    ".sh",
    ".toml",
    ".conf",
    ".template",
    ".html",
    ".css",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    ".cache",
    "dist",
    "app_logs",
    "backups",
    "__pycache__",
    ".claude",
    ".pytest_cache",
    ".ruff_cache",
}
SKIP_FILES = {
    "pnpm-lock.yaml",
    "uv.lock",
    "openapi.json",
    "schema.d.ts",
    "events.schema.json",
    "ai_markers.txt",
}
SKIP_NAMELESS = {"maxapp", "deploy.sh"}


def _patterns() -> list[re.Pattern[str]]:
    out: list[re.Pattern[str]] = []
    for line in MARKERS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(re.compile(line, re.IGNORECASE))
    return out


def _files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.name in SKIP_FILES:
            continue
        if path.suffix in SCANNED_SUFFIXES or path.name in SKIP_NAMELESS:
            result.append(path)
    return result


def test_no_ai_markers() -> None:
    patterns = _patterns()
    assert patterns, "список маркеров пуст"
    hits: list[str] = []
    for path in _files():
        # Сам тест содержит примеры шаблонов в докстринге; пропускаем его.
        if path == Path(__file__):
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            for pattern in patterns:
                if pattern.search(line):
                    hits.append(
                        f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:100]}  [{pattern.pattern}]"
                    )
                    break
    assert not hits, "маркеры сгенерированного текста:\n" + "\n".join(hits[:50])
