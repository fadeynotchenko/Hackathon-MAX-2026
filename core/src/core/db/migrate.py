"""Применение миграций Alembic из процесса api.

Alembic синхронный и его env.py сам поднимает event loop, поэтому команда
выполняется в отдельном потоке. Гонку нескольких воркеров снимает
advisory-lock в env.py.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from core.logs import biz_info

logger = logging.getLogger(__name__)

CORE_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = CORE_ROOT / "alembic.ini"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Логи процесса уже настроены setup_logging; env.py не должен их сбрасывать.
    cfg.attributes["configure_logger"] = False
    return cfg


def _upgrade_head() -> None:
    command.upgrade(alembic_config(), "head")


async def upgrade_to_head() -> None:
    await asyncio.to_thread(_upgrade_head)
    biz_info(logger, "db.migrations.applied")
