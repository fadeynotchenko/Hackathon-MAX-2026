"""Генерация корневого ``.env.example`` из реестра core.config.env_spec.

    uv run python -m core.scripts.gen_env_example          # перезаписать
    uv run python -m core.scripts.gen_env_example --check   # только сверить

.env.example лежит в корне репозитория: он описывает весь compose-стек, а
реестр живёт в core, потому что это единственный Python-сервис. Файл обязан
совпадать с рендером (tests/config/test_env_spec.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.config.env_spec import ENV_SPEC, GROUP_ORDER, GROUP_TITLES, EnvVar

CORE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = CORE_ROOT.parent
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

_HEADER = """\
# =============================================================================
# MAX mini app — пример окружения (сгенерирован, руками не править).
#
# Источник правды: core/src/core/config/env_spec.py
# Перегенерация:   cd core && uv run python -m core.scripts.gen_env_example
# Проверка:        cd core && uv run python -m core.scripts.gen_env_example --check
#
# Скопируй в .env и заполни значения. [required: ...] — без переменной
# перечисленные сервисы не стартуют. Секреты здесь — плейсхолдеры.
# =============================================================================
"""


def _value_for(var: EnvVar) -> str:
    if var.secret:
        return var.example or "change-me"
    if var.example is not None:
        return var.example
    return var.default or ""


def render() -> str:
    by_group: dict[str, list[EnvVar]] = {}
    for var in ENV_SPEC:
        by_group.setdefault(var.group, []).append(var)

    lines = [_HEADER]
    for group in (*GROUP_ORDER, *(g for g in by_group if g not in GROUP_ORDER)):
        variables = by_group.get(group)
        if not variables:
            continue
        title = GROUP_TITLES.get(group, group)
        lines.append(f"# --- {title} " + "-" * max(0, 60 - len(title)))
        for var in variables:
            tags = [
                "required: " + ", ".join(sorted(var.required_for))
                if var.required_for
                else "optional",
                var.type,
            ]
            lines.append(f"# {var.description} [{'; '.join(tags)}]")
            if var.notes:
                lines.append(f"#   note: {var.notes}")
            if var.owner:
                lines.append(f"#   owner: {var.owner}")
            lines.append(f"{var.name}={_value_for(var)}")
            lines.append("")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    rendered = render()
    if "--check" in argv:
        current = ENV_EXAMPLE_PATH.read_text(encoding="utf-8") if ENV_EXAMPLE_PATH.exists() else ""
        if current != rendered:
            print(
                ".env.example устарел: uv run python -m core.scripts.gen_env_example",
                file=sys.stderr,
            )
            return 1
        print(".env.example актуален")
        return 0
    ENV_EXAMPLE_PATH.write_text(rendered, encoding="utf-8")
    print(f"записан {ENV_EXAMPLE_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
