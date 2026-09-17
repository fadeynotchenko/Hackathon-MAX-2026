"""Миграции из процесса api не должны сбрасывать настроенное логирование."""

from __future__ import annotations

from core.db.migrate import ALEMBIC_INI, MIGRATIONS_DIR, alembic_config


def test_alembic_config_keeps_process_logging() -> None:
    cfg = alembic_config()
    assert cfg.attributes["configure_logger"] is False
    assert cfg.get_main_option("script_location") == str(MIGRATIONS_DIR)
    assert ALEMBIC_INI.exists()
    env = (MIGRATIONS_DIR / "env.py").read_text(encoding="utf-8")
    assert 'config.attributes.get("configure_logger", True)' in env, (
        "env.py обязан уважать флаг, иначе fileConfig снимет хендлеры root-логгера"
    )
    assert "pg_advisory_xact_lock" in env
