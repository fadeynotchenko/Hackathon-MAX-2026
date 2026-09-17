"""Подписанный initData для запуска production-сборки мини-аппа в обычном браузере.

    uv run python -m core.scripts.dev_init_data --user-id 1 --first-name Dev --username dev

Печатает строку для VITE_DEV_INIT_DATA в .env. В dev-режиме (vite dev-server)
этот шаг не нужен: мини-апп сам берёт initData у ручки GET /api/v1/dev/init-data.
"""

from __future__ import annotations

import argparse

from core.config.env import get_env
from core.domain.initdata import build_dev_init_data


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--first-name", default="Dev")
    parser.add_argument("--last-name", default="User")
    parser.add_argument("--username", default="dev")
    parser.add_argument("--start-param", default="")
    args = parser.parse_args()

    token = get_env("MAX_BOT_TOKEN")
    if not token:
        parser.error("MAX_BOT_TOKEN не задан (нужен тот же токен, что у API)")
    init_data = build_dev_init_data(
        token,
        user_id=args.user_id,
        first_name=args.first_name,
        last_name=args.last_name or None,
        username=args.username or None,
        start_param=args.start_param or None,
    )
    print(f"VITE_DEV_INIT_DATA={init_data}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
