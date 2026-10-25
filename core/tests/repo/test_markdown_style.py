"""Стиль документации: без длинных тире, эмодзи и точки в конце абзаца.

Правило владельца проекта для всех md-файлов репозитория. Код внутри
блоков ``` не проверяется: там свои правила языка и комментариев.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRS = {".git", ".venv", "node_modules", ".cache", "dist", ".claude", "app_logs", "backups"}
# Инструкции агента живут только локально (см. .gitignore) и правилам репозитория не подчиняются.
SKIP_FILES = {"AGENTS.md", "CLAUDE.md"}

DASHES = re.compile("[–—]")
EMOJI = re.compile("[☀-➿⬀-⯿️\U0001f000-\U0001faff]")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
INLINE_CODE = re.compile(r"`[^`]*`")


def _markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)
        and path.name not in SKIP_FILES
    )


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """Строки текста вне блоков кода, с номерами."""
    lines: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            lines.append((number, line))
    return lines


def _block_ends(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Последняя строка каждого абзаца и каждого пункта списка."""
    ends: list[tuple[int, str]] = []
    previous: tuple[int, str] | None = None
    for number, line in [*lines, (0, "")]:
        starts_block = not line.strip() or LIST_ITEM.match(line) or line.lstrip().startswith("#")
        if starts_block and previous is not None:
            ends.append(previous)
            previous = None
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "|", "<", ">")):
            previous = None
            continue
        previous = (number, stripped)
    return ends


def test_markdown_files_found() -> None:
    names = {path.relative_to(ROOT).as_posix() for path in _markdown_files()}
    assert {"README.md", "docs/ARCHITECTURE.md"} <= names


def test_no_long_dashes_or_emoji() -> None:
    hits: list[str] = []
    for path in _markdown_files():
        for number, line in _prose_lines(path.read_text(encoding="utf-8")):
            if DASHES.search(line) or EMOJI.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}")
    assert not hits, "длинное тире или эмодзи в документации:\n" + "\n".join(hits)


def test_paragraphs_and_list_items_end_without_period() -> None:
    hits: list[str] = []
    for path in _markdown_files():
        for number, line in _block_ends(_prose_lines(path.read_text(encoding="utf-8"))):
            # Номер пункта («3.») сам по себе не точка в конце: снимаем маркер до кода.
            text = INLINE_CODE.sub("", LIST_ITEM.sub("", line)).rstrip()
            if text.endswith(".") and not text.endswith(".."):
                hits.append(f"{path.relative_to(ROOT)}:{number}: …{line[-60:]}")
    assert not hits, "точка в конце абзаца или пункта:\n" + "\n".join(hits)
