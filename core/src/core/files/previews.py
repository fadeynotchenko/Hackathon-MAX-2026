"""Картинки страниц документа: как лист выглядит в PDF у контрагента.

Картинка получается из того же PDF, что уходит в чат (LibreOffice), а не из
отдельной вёрстки: иначе предпросмотр и файл разошлись бы по виду. Страницы
растеризует ``pdftoppm`` (poppler-utils) — он стоит в образе рядом с
LibreOffice, отдельной Python-библиотеки с нативным кодом не нужно.

Конвертация стоит секунды, поэтому результат кешируется на диске по ключу
редакции: та же редакция документа или пустой бланк шаблона конвертируется один
раз, правка поля даёт новый ключ. Ключ даёт вызывающий: байты одной и той
же сборки DOCX различаются временем внутри zip. Одновременных LibreOffice не
больше двух — на двух ядрах прод-сервера больше только мешают друг другу и API.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from core.files.errors import PdfUnavailableError

# Ширина картинки в пикселях: карточка каталога и лист во весь экран (A4 при 150 dpi).
PREVIEW_WIDTHS = {"thumb": 480, "page": 1240}
PDFTOPPM_BIN = "pdftoppm"
# Сколько редакций держать в кеше: правка поля даёт новую, старые не нужны.
CACHE_LIMIT = 400

_conversions = asyncio.Semaphore(2)
_locks: dict[str, asyncio.Lock] = {}

ToPdf = Callable[[bytes], Awaitable[bytes]]


@dataclass(frozen=True)
class PreviewPage:
    data: bytes
    page: int
    pages: int


async def pdf_to_jpeg(pdf: bytes, *, width: int, timeout_seconds: int) -> list[bytes]:
    """Все страницы PDF — JPEG заданной ширины, по порядку."""
    if shutil.which(PDFTOPPM_BIN) is None:
        raise PdfUnavailableError(f"растеризатор {PDFTOPPM_BIN!r} не найден")
    with TemporaryDirectory(prefix="maxapp-pages-") as tmp:
        work = Path(tmp)
        source = work / "document.pdf"
        source.write_bytes(pdf)
        process = await asyncio.create_subprocess_exec(
            PDFTOPPM_BIN,
            "-jpeg",
            "-jpegopt",
            "quality=85",
            "-scale-to-x",
            str(width),
            "-scale-to-y",
            "-1",
            str(source),
            str(work / "page"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise PdfUnavailableError("растеризация не уложилась в таймаут") from exc
        pages = _read_pages(work)
        if process.returncode != 0 or not pages:
            detail = stderr.decode(errors="replace").strip() or f"код {process.returncode}"
            raise PdfUnavailableError(f"pdftoppm не отрисовал страницы: {detail}")
        return pages


def _read_pages(work: Path) -> list[bytes]:
    # Имена page-1.jpg … page-12.jpg дополняются нулями по числу страниц,
    # поэтому порядок — по номеру, а не по строке.
    found = sorted(work.glob("page-*.jpg"), key=lambda p: int(p.stem.rpartition("-")[2]))
    return [page.read_bytes() for page in found]


class PreviewCache:
    """Картинки страниц по ключу редакции в ``<documents_dir>/previews/<ключ>/``."""

    def __init__(self, root: Path, *, timeout_seconds: int) -> None:
        self.root = root / "previews"
        self.timeout_seconds = timeout_seconds

    async def page(
        self, docx: bytes, *, size: str, page: int, to_pdf: ToPdf, key: str | None = None
    ) -> PreviewPage | None:
        """Страница ``page`` (с единицы); ``None`` — такой страницы в документе нет.

        ``key`` — ключ редакции от вызывающего: байты DOCX для одной редакции
        разные (время в zip), поэтому хеш байтов — только запасной ключ."""
        key = key or hashlib.sha256(docx).hexdigest()[:32]
        folder = self.root / key
        count = self._count(folder, size)
        if count is None:
            lock = _locks.setdefault(key, asyncio.Lock())
            async with lock:
                count = self._count(folder, size)
                if count is None:
                    count = await self._render(folder, docx, size=size, to_pdf=to_pdf)
            _locks.pop(key, None)
        if not 1 <= page <= count:
            return None
        return PreviewPage((folder / f"{size}-{page}.jpg").read_bytes(), page, count)

    @staticmethod
    def _count(folder: Path, size: str) -> int | None:
        marker = folder / f"{size}.count"
        return int(marker.read_text()) if marker.exists() else None

    async def _render(self, folder: Path, docx: bytes, *, size: str, to_pdf: ToPdf) -> int:
        pdf_path = folder / "document.pdf"
        pdf = _cached_pdf(pdf_path)
        if pdf is None:
            async with _conversions:
                pdf = await to_pdf(docx)
            pdf_path.write_bytes(pdf)
        images = await pdf_to_jpeg(
            pdf, width=PREVIEW_WIDTHS[size], timeout_seconds=self.timeout_seconds
        )
        for number, image in enumerate(images, start=1):
            (folder / f"{size}-{number}.jpg").write_bytes(image)
        # Счётчик пишется последним: по нему видно, что страницы на диске целиком.
        (folder / f"{size}.count").write_text(str(len(images)))
        self._prune()
        return len(images)

    def _prune(self) -> None:
        folders = sorted(
            (item for item in self.root.iterdir() if item.is_dir()),
            key=lambda item: item.stat().st_mtime,
        )
        for stale in folders[:-CACHE_LIMIT]:
            shutil.rmtree(stale, ignore_errors=True)


def _cached_pdf(pdf_path: Path) -> bytes | None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    return pdf_path.read_bytes() if pdf_path.exists() else None
