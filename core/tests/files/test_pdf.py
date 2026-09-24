"""Конвертация в PDF: зависший LibreOffice не переживает отмену запроса."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from core.files import PdfUnavailableError, convert_to_pdf


def _fake_soffice(tmp_path: Path) -> tuple[str, Path]:
    pid_file = tmp_path / "pid"
    script = tmp_path / "soffice"
    script.write_text(f"#!/bin/sh\necho $$ > {pid_file}\nexec sleep 30\n")
    script.chmod(0o755)
    return str(script), pid_file


async def _pid(pid_file: Path) -> int:
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text().strip():
            return int(pid_file.read_text())
        await asyncio.sleep(0.02)
    raise AssertionError("фальшивый soffice не запустился")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_cancelled_conversion_kills_libreoffice(tmp_path: Path) -> None:
    soffice, pid_file = _fake_soffice(tmp_path)
    task = asyncio.create_task(convert_to_pdf(b"docx", soffice_bin=soffice, timeout_seconds=30))
    pid = await _pid(pid_file)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not _alive(pid), "процесс не должен работать после отмены запроса"


async def test_timed_out_conversion_is_reaped(tmp_path: Path) -> None:
    soffice, pid_file = _fake_soffice(tmp_path)
    with pytest.raises(PdfUnavailableError):
        await convert_to_pdf(b"docx", soffice_bin=soffice, timeout_seconds=1)
    assert not _alive(await _pid(pid_file))
