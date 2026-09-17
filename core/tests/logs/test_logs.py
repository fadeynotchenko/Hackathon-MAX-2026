"""Единый формат логов: JSON-схема, контекст, pretty-вывод, файл с ротацией."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from core.logs import (
    bind_context,
    biz_error,
    biz_info,
    clear_context,
    setup_logging,
)
from core.logs.setup import JsonFormatter, PrettyFormatter


@pytest.fixture(autouse=True)
def _clean_context():
    clear_context()
    yield
    clear_context()


def _record(logger_name: str, level: int, msg: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord(logger_name, level, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_schema() -> None:
    bind_context(request_id="rid-1", user_id=5)
    logger = logging.getLogger("test.json")
    captured: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = captured.append  # type: ignore[method-assign]
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        biz_info(logger, "auth.login.ok", max_user_id=42, note="x" * 600)
    finally:
        logger.removeHandler(handler)

    payload = json.loads(JsonFormatter("api").format(captured[0]))
    assert payload["service"] == "api"
    assert payload["level"] == "info"
    assert payload["event"] == "auth.login.ok"
    assert payload["msg"] == "auth.login.ok"
    assert payload["request_id"] == "rid-1"
    assert payload["user_id"] == 5
    assert payload["max_user_id"] == 42
    assert payload["ts"].endswith("Z")
    # Длинные строки обрезаются, чтобы одна запись не раздувала журнал.
    assert len(payload["note"]) == 500


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record("x", logging.ERROR, "failed", event="job.failed", fields={})
        record.exc_info = sys.exc_info()
    payload = json.loads(JsonFormatter("jobs").format(record))
    assert payload["err"]["type"] == "ValueError"
    assert payload["err"]["message"] == "boom"
    assert "Traceback" in payload["err"]["stack"]


def test_pretty_formatter_mentions_event_and_fields() -> None:
    record = _record(
        "api.access", logging.INFO, "http.request", event="http.request", fields={"status": 200}
    )
    line = PrettyFormatter("api", color=False).format(record)
    assert "INFO" in line and "http.request" in line and "status=200" in line
    assert "\033[" not in line


def test_setup_logging_writes_json_file(tmp_path: Path) -> None:
    logger = setup_logging("svc", level="INFO", fmt="json", log_dir=tmp_path)
    biz_info(logger, "svc.hello", answer=42)
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = (tmp_path / "svc.log").read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(content[-1])
    assert payload["event"] == "svc.hello" and payload["answer"] == 42
    setup_logging("svc", level="INFO", fmt="json", log_dir="")


def test_biz_error_with_exc_info(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test.err")
    with caplog.at_level(logging.ERROR, logger="test.err"):
        try:
            raise KeyError("k")
        except KeyError:
            biz_error(logger, "x.failed", exc_info=True)
    assert caplog.records[0].exc_info is not None


def test_rotated_file_name_matches_bot_pattern() -> None:
    from core.logs.setup import _gzip_namer

    assert _gzip_namer("/var/log/app/api.log.2026-09-16") == "/var/log/app/api.2026-09-16.log.gz"
    assert _gzip_namer("weird") == "weird.gz"
