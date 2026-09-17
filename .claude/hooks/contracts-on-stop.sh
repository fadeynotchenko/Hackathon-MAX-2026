#!/usr/bin/env bash
# Stop: архитектурные контракты и замки репозитория перед концом хода.
#   изменились *.py / compose / gateway / docs → lint-imports core + pytest core/tests/repo
#   изменились *.ts/tsx                          → depcruise
# Нарушение возвращается агенту (exit 2). stop_hook_active защищает от цикла.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
# Без jq хук не может разобрать payload: лучше сказать об этом, чем молча пропустить.
command -v jq >/dev/null || { echo "hook: jq не установлен (brew install jq)" >&2; exit 0; }

payload=$(cat)
[ "$(printf '%s' "$payload" | jq -r '.stop_hook_active // false')" = "true" ] && exit 0

# -uall: новые файлы перечисляются по одному, а не свёрнутым каталогом.
changed=$(git status --porcelain -uall 2>/dev/null | awk '{print $2}')
[ -n "$changed" ] || exit 0

fail=0
if printf '%s\n' "$changed" | grep -qE '\.py$|pyproject\.toml$|docker-compose|gateway/|contracts/|\.md$'; then
  if [ -x core/.venv/bin/lint-imports ]; then
    if ! out=$(cd core && .venv/bin/lint-imports --cache-dir .cache/import-linter 2>&1); then
      printf 'import-linter: контракты слоёв core нарушены\n%s\n' "$out" >&2; fail=1
    fi
  fi
  if [ -x core/.venv/bin/python ]; then
    if ! out=$(cd core && .venv/bin/python -m pytest tests/repo -q -p no:cacheprovider 2>&1); then
      printf 'core/tests/repo: замки репозитория красные\n%s\n' "$(printf '%s' "$out" | tail -40)" >&2; fail=1
    fi
  fi
fi
if printf '%s\n' "$changed" | grep -qE '\.(ts|tsx)$'; then
  if [ -x node_modules/.bin/depcruise ]; then
    if ! out=$(node_modules/.bin/depcruise bot/src web/src --config .dependency-cruiser.cjs 2>&1); then
      printf 'dependency-cruiser: контракты нарушены\n%s\n' "$out" >&2; fail=1
    fi
  fi
fi
[ "$fail" -eq 0 ] || exit 2
exit 0
