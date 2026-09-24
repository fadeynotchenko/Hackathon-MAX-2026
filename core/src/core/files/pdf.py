"""Конвертация DOCX → PDF через LibreOffice.

Отдельного рендера PDF нет намеренно: два независимых генератора неизбежно
разошлись бы по виду, а пользователь отправляет контрагенту оба файла.
LibreOffice запускается разово на файл; профиль пользователя кладём во
временный каталог, иначе параллельные вызовы дерутся за общий профиль.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from core.files.errors import PdfUnavailableError


async def convert_to_pdf(docx_bytes: bytes, *, soffice_bin: str, timeout_seconds: int) -> bytes:
    if shutil.which(soffice_bin) is None:
        raise PdfUnavailableError(f"конвертер {soffice_bin!r} не найден")

    with TemporaryDirectory(prefix="maxapp-pdf-") as tmp:
        work = Path(tmp)
        source = work / "document.docx"
        source.write_bytes(docx_bytes)
        process = await asyncio.create_subprocess_exec(
            soffice_bin,
            f"-env:UserInstallation=file://{work / 'profile'}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work),
            str(source),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError as exc:
            await _stop(process)
            raise PdfUnavailableError("конвертация PDF не уложилась в таймаут") from exc
        except asyncio.CancelledError:
            # Запрос отменили (таймаут API): LibreOffice не должен работать дальше
            # в каталоге, который сейчас удалится, и копиться процессами.
            await _stop(process)
            raise

        result = work / "document.pdf"
        if process.returncode != 0 or not result.exists():
            detail = stderr.decode(errors="replace").strip() or f"код {process.returncode}"
            raise PdfUnavailableError(f"LibreOffice не собрал PDF: {detail}")
        return result.read_bytes()


async def _stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.kill()
        await process.wait()
