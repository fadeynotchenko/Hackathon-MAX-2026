"""Документ в оформлении присланного PDF: значения меняются прямо на листе.

PDF не редактируется как DOCX: текста-абзаца в нём нет, только глифы по
координатам. Перевод PDF в DOCX (LibreOffice) разваливал вёрстку — текст
наезжал, подписи пропадали, — поэтому лист остаётся исходным, а поверх места
значения кладётся белая плашка и новое значение тем же кеглем. Прежний текст
места не должен остаться в файле — иначе прежний клиент читался бы при
копировании и поиске, — поэтому до плашки он вырезается из страницы (pdfium):
объект, который весь — значение, удаляется, а из объекта, где значение слито с
подписью («ИНН 7707083893»), вырезается только значение. Место на листе
ищется по тому же ``Place`` (текст перед значением и само значение), что и в
DOCX; пробелы в тексте PDF расставлены как попало, поэтому сравнение идёт по
символам без пробелов.

Шрифт — метрически совместимый с исходным: засечки у Times и других serif,
иначе Arial-подобный; полужирный — если исходный был полужирным. Нет ни одного
TTF с кириллицей — ``PdfUnavailableError``: подставить нечем, латинские
квадраты вместо текста хуже честного отказа.
"""

from __future__ import annotations

import ctypes
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from core.domain.places import Place
from core.files.errors import PdfUnavailableError, TemplateFileError

# Шрифты по ролям; первый найденный файл выигрывает. Liberation и DejaVu стоят в
# прод-образе, системные — у разработчика на macOS.
FONT_FILES: dict[str, tuple[str, ...]] = {
    "sans": (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ),
    "sans-bold": (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
    "serif": (
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    ),
    "serif-bold": (
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    ),
}
_SERIF = re.compile(r"times|serif|georgia|cambria|garamond|roman", re.IGNORECASE)
_BOLD = re.compile(r"bold|black|heavy|semibold", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
# Доля объекта на месте значения, при которой он удаляется целиком, если его
# текст не прочитать.
_INSIDE = 0.6
# Поля страницы, за которые значение не выходит: длинное сжимается по кеглю.
_MARGIN = 20.0
_MIN_SIZE = 6.0


@dataclass(frozen=True)
class _Spot:
    page: int
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    role: str
    text: str
    # Прежний текст места на этой строке, без пробелов: по нему он вырезается
    # из объекта, где стоит вместе с подписью.
    original: str = ""


def available() -> bool:
    return all(_font_file(role) is not None for role in FONT_FILES)


def _font_file(role: str) -> str | None:
    return next((path for path in FONT_FILES[role] if Path(path).exists()), None)


def _register(role: str) -> str:
    name = f"maxapp-{role}"
    if name not in pdfmetrics.getRegisteredFontNames():
        path = _font_file(role)
        if path is None:
            raise PdfUnavailableError(f"нет шрифта с кириллицей для роли {role!r}")
        pdfmetrics.registerFont(TTFont(name, path))
    return name


def _role(fontname: str) -> str:
    base = "serif" if _SERIF.search(fontname) else "sans"
    return f"{base}-bold" if _BOLD.search(fontname) else base


def _spots(
    pdf: bytes, places: Sequence[tuple[str, Place]], values: Mapping[str, str]
) -> list[_Spot]:
    """Места значений на страницах. Длинные места ищутся первыми и занятые
    символы второй раз не отдаются — как ``place_spans`` в тексте."""
    ordered = sorted(places, key=lambda item: -len(item[1].before + item[1].text))
    spots: list[_Spot] = []
    try:
        document = pdfplumber.open(io.BytesIO(pdf))
    except Exception as exc:
        raise TemplateFileError(f"PDF-образец не открылся: {exc}") from exc
    with document:
        for number, page in enumerate(document.pages):
            chars = [char for char in page.chars if char["text"].strip()]
            flat = "".join(char["text"] for char in chars)
            taken = [False] * len(chars)
            for key, place in ordered:
                value_part = _SPACE.sub("", place.text)
                if not value_part:
                    continue
                before = _SPACE.sub("", place.before)
                needle = before + value_part
                start = flat.find(needle)
                while start != -1:
                    begin, end = start + len(before), start + len(needle)
                    if not any(taken[begin:end]):
                        for index in range(begin, end):
                            taken[index] = True
                        spots.extend(_line_spots(number, chars[begin:end], values.get(key, "")))
                    start = flat.find(needle, start + len(needle))
    return spots


def _line_spots(page: int, chars: list[dict[str, object]], text: str) -> list[_Spot]:
    """Значение могло занимать в образце несколько строк: каждая строка
    закрывается своей плашкой, а новое значение пишется в первой."""
    lines: list[list[dict[str, object]]] = []
    for char in chars:
        if lines and abs(float(lines[-1][0]["top"]) - float(char["top"])) < 2:  # type: ignore[arg-type]
            lines[-1].append(char)
        else:
            lines.append([char])
    spots = []
    for index, line in enumerate(lines):
        first = line[0]
        spots.append(
            _Spot(
                page=page,
                x0=min(float(c["x0"]) for c in line),  # type: ignore[arg-type]
                x1=max(float(c["x1"]) for c in line),  # type: ignore[arg-type]
                top=min(float(c["top"]) for c in line),  # type: ignore[arg-type]
                bottom=max(float(c["bottom"]) for c in line),  # type: ignore[arg-type]
                size=float(first["size"]),  # type: ignore[arg-type]
                role=_role(str(first.get("fontname", ""))),
                text=text if index == 0 else "",
                original="".join(str(c["text"]) for c in line),
            )
        )
    return spots


def fill_pdf(
    pdf: bytes, *, places: Sequence[tuple[str, Place]], values: Mapping[str, str]
) -> bytes:
    """Копия PDF, где на местах полей стоят ``values[key]`` (пустая строка —
    место просто закрыто)."""
    spots = _spots(pdf, places, values)
    reader = PdfReader(io.BytesIO(_strip(pdf, spots)))
    writer = PdfWriter()
    for number, page in enumerate(reader.pages):
        mine = [spot for spot in spots if spot.page == number]
        if mine:
            page.merge_page(_overlay(page, mine))
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _strip(pdf: bytes, spots: list[_Spot]) -> bytes:
    """Удалить текст образца, стоящий на местах значений."""
    if not spots:
        return pdf
    document = pdfium.PdfDocument(pdf)
    try:
        for number in range(len(document)):
            mine = [spot for spot in spots if spot.page == number]
            if mine:
                _strip_page(document, number, mine)
        out = io.BytesIO()
        document.save(out)
        return out.getvalue()
    finally:
        document.close()


def _strip_page(document: pdfium.PdfDocument, number: int, spots: list[_Spot]) -> None:
    # pdfium следит за деревом объектов: удалённый объект и страницу закрываем
    # сами и по порядку, иначе сборщик мусора закрывает их после документа.
    page = document[number]
    textpage = page.get_textpage()
    try:
        height = page.get_height()
        texts = list(page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_TEXT], max_depth=1))
        doomed = []
        changed = False
        for obj in texts:
            touched = [spot for spot in spots if _overlaps(obj.get_bounds(), spot, height)]
            if not touched:
                continue
            text = _object_text(obj, textpage)
            cut = text
            for spot in touched:
                cut = _without(cut, spot.original)
            if cut != text and cut.strip():
                # Значение слито с подписью в один объект («ИНН 7707083893»):
                # вырезается только значение, подпись остаётся на месте.
                changed = _set_text(obj, cut.rstrip()) or changed
            elif cut != text or _covered(obj.get_bounds(), touched, height):
                # Объект — само значение (или его текст не прочитать, но он
                # почти целиком на месте значения): удаляется целиком.
                doomed.append(obj)
        for obj in doomed:
            page.remove_obj(obj)
            obj.close()
        changed = changed or bool(doomed)
        if changed:
            page.gen_content()
    finally:
        textpage.close()
        page.close()


def _overlaps(bounds: tuple[float, float, float, float], spot: _Spot, height: float) -> bool:
    left, bottom, right, top = bounds
    y0, y1 = height - spot.bottom, height - spot.top
    return right > spot.x0 and left < spot.x1 and top > y0 and bottom < y1


def _object_text(obj: pdfium.PdfObject, textpage: pdfium.PdfTextPage) -> str:
    size = pdfium_c.FPDFTextObj_GetText(obj.raw, textpage.raw, None, 0)
    if size <= 2:
        return ""
    buffer = ctypes.create_string_buffer(size)
    pdfium_c.FPDFTextObj_GetText(
        obj.raw, textpage.raw, ctypes.cast(buffer, ctypes.POINTER(pdfium_c.FPDF_WCHAR)), size
    )
    return buffer.raw[: size - 2].decode("utf-16-le", errors="ignore")


def _set_text(obj: pdfium.PdfObject, text: str) -> bool:
    encoded = (text + "\x00").encode("utf-16-le")
    buffer = ctypes.create_string_buffer(encoded, len(encoded))
    return bool(
        pdfium_c.FPDFText_SetText(obj.raw, ctypes.cast(buffer, ctypes.POINTER(pdfium_c.FPDF_WCHAR)))
    )


def _without(text: str, needle: str) -> str:
    """Вырезать ``needle`` из ``text``, не считая пробелов: в PDF они стоят не
    так, как в тексте, по которому нашлось место."""
    if not needle:
        return text
    positions = [index for index, char in enumerate(text) if not char.isspace()]
    flat = "".join(text[index] for index in positions)
    start = flat.find(needle)
    if start == -1:
        return text
    begin, end = positions[start], positions[start + len(needle) - 1] + 1
    return text[:begin] + text[end:]


def _covered(bounds: tuple[float, float, float, float], spots: list[_Spot], height: float) -> bool:
    left, bottom, right, top = bounds
    area = max((right - left) * (top - bottom), 1e-6)
    for spot in spots:
        # pdfplumber считает сверху вниз, pdfium — снизу вверх.
        x0, x1 = spot.x0 - 1, spot.x1 + 1
        y0, y1 = height - spot.bottom - 1, height - spot.top + 1
        width = max(0.0, min(right, x1) - max(left, x0))
        tall = max(0.0, min(top, y1) - max(bottom, y0))
        if width * tall / area > _INSIDE:
            return True
    return False


def _overlay(page: object, spots: list[_Spot]):  # type: ignore[no-untyped-def]
    box = page.mediabox  # type: ignore[attr-defined]
    width, height = float(box.width), float(box.height)
    buffer = io.BytesIO()
    sheet = canvas.Canvas(buffer, pagesize=(width, height))
    for spot in spots:
        # pdfplumber считает сверху вниз, PDF — снизу вверх.
        y_bottom = height - spot.bottom
        sheet.setFillColorRGB(1, 1, 1)
        sheet.rect(
            spot.x0 - 0.5,
            y_bottom - 0.5,
            spot.x1 - spot.x0 + 1,
            spot.bottom - spot.top + 1,
            stroke=0,
            fill=1,
        )
        if not spot.text:
            continue
        font = _register(spot.role)
        size = spot.size
        room = width - _MARGIN - spot.x0
        while size > _MIN_SIZE and pdfmetrics.stringWidth(spot.text, font, size) > room:
            size -= 0.5
        sheet.setFillColorRGB(0, 0, 0)
        sheet.setFont(font, size)
        # Базовая линия — на пятой части кегля выше низа глифов.
        sheet.drawString(spot.x0, y_bottom + spot.size * 0.2, spot.text)
    sheet.save()
    return PdfReader(io.BytesIO(buffer.getvalue())).pages[0]
