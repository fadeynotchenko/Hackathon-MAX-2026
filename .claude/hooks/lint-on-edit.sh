#!/usr/bin/env bash
# PostToolUse: линтер по отредактированному файлу, по расширению.
#   *.py        → ruff check --fix + ruff format
#   *.ts/*.tsx  → prettier --write + eslint --fix
#   *.json/*.yml/*.md/*.css → prettier --write
# Неустранимые замечания уходят обратно агенту (stderr + exit 2), чтобы он
# исправил их до конца хода. Форматирование применяется молча.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
# Без jq хук не может разобрать payload: лучше сказать об этом, чем молча пропустить.
command -v jq >/dev/null || { echo "hook: jq не установлен (brew install jq)" >&2; exit 0; }

payload=$(cat)
file=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // .tool_response.filePath // empty')
[ -n "$file" ] && [ -f "$file" ] || exit 0

case "$file" in
  *.py)
    # Python живёт только в сервисе core; ruff берёт конфиг из core/pyproject.toml.
    [ -x core/.venv/bin/ruff ] || exit 0
    # --force-exclude: исключения конфига (migrations/versions) действуют и на явный путь.
    core/.venv/bin/ruff check --fix --force-exclude --quiet "$file" >/dev/null 2>&1 || true
    core/.venv/bin/ruff format --force-exclude --quiet "$file" >/dev/null 2>&1 || true
    if ! out=$(core/.venv/bin/ruff check --force-exclude "$file" 2>&1); then
      printf 'ruff: неустранимые замечания в %s\n%s\n' "$file" "$out" >&2
      exit 2
    fi
    ;;
  *.ts|*.tsx)
    [ -x node_modules/.bin/eslint ] || exit 0
    node_modules/.bin/prettier --write --log-level silent "$file" >/dev/null 2>&1 || true
    node_modules/.bin/eslint --fix "$file" >/dev/null 2>&1 || true
    if ! out=$(node_modules/.bin/eslint "$file" 2>&1); then
      printf 'eslint: неустранимые замечания в %s\n%s\n' "$file" "$out" >&2
      exit 2
    fi
    ;;
  *.json|*.yml|*.yaml|*.md|*.css)
    [ -x node_modules/.bin/prettier ] || exit 0
    node_modules/.bin/prettier --write --log-level silent "$file" >/dev/null 2>&1 || true
    ;;
esac
exit 0
