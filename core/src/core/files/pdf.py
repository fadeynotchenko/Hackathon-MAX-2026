"""Конвертация DOCX → PDF через LibreOffice.

Отдельного рендера PDF нет намеренно: два независимых генератора неизбежно
разошлись бы по виду, а пользователь отправляет контрагенту оба файла.
LibreOffice запускается разово на файл; профиль пользователя кладём во
временный каталог, иначе параллельные вызовы дерутся за общий профиль.

Одновременно работает не больше ``MAX_PARALLEL_CONVERSIONS`` конвертеров:
библиотека шаблонов просит дюжину листов разом, и на проде LibreOffice падал
«Cannot fork» — каждый запуск плодит процессы и упирается в лимит pids
контейнера. Остальные ждут очереди: лист приходит на секунды позже, а не ошибкой.
"""

from __future__ import annotations

import asyncio
import shutil
import weakref
from pathlib import Path
from tempfile import TemporaryDirectory

from core.files.errors import PdfUnavailableError

# Под два CPU прод-сервера: больше параллельных LibreOffice только мешают друг другу.
MAX_PARALLEL_CONVERSIONS = 2
# Очередь своя у каждого цикла событий: семафор, раз дождавшийся в одном цикле,
# в другом (тесты, повторный старт) бросил бы RuntimeError.
_queues: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


def _queue() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    queue = _queues.get(loop)
    if queue is None:
        queue = _queues[loop] = asyncio.Semaphore(MAX_PARALLEL_CONVERSIONS)
    return queue


async def convert_to_pdf(docx_bytes: bytes, *, soffice_bin: str, timeout_seconds: int) -> bytes:
    if shutil.which(soffice_bin) is None:
        raise PdfUnavailableError(f"конвертер {soffice_bin!r} не найден")
    async with _queue():
        return await _convert(docx_bytes, soffice_bin=soffice_bin, timeout_seconds=timeout_seconds)


async def _convert(docx_bytes: bytes, *, soffice_bin: str, timeout_seconds: int) -> bytes:
    with TemporaryDirectory(prefix="maxapp-pdf-") as tmp:
        work = Path(tmp)
        source = work / "document.docx"
        source.write_bytes(docx_bytes)
        try:
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
        except OSError as exc:
            # «Cannot fork» до старта LibreOffice — та же недоступность PDF, а не 500.
            raise PdfUnavailableError(f"LibreOffice не запустился: {exc}") from exc
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
