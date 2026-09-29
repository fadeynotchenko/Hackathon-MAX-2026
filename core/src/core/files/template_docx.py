"""Шаблон-файл DOCX: текст образца и сборка документа в его оформлении.

Документ по такому шаблону собирается не заново, а в копии файла компании:
логотип, шрифты, таблицы и колонтитулы остаются как были, меняются только
места для данных. Word режет текст абзаца на куски (runs) по своему усмотрению —
«ООО «Альфа»» легко оказывается в трёх кусках с разным оформлением, — поэтому
места ищутся в тексте абзаца целиком, а замена правит только затронутые куски:
значение встаёт в первый из них и берёт его оформление.

Сборка идёт в два прохода: места → маркеры ``{{key}}``, маркеры → значения.
Иначе значение одного поля, похожее на место другого, заменилось бы повторно.
Маркер может просить вариант записи значения — ``{{total|words}}``: сумму
прописью, дату словами; варианты считает домен (``fill_context``).

Условный кусок ``[[, КПП {{seller_kpp}}]]`` исчезает вместе с подписью, когда
значение внутри пустое; абзац, от которого осталась одна подпись, убирается,
а строка таблицы — когда опустели все её ячейки с данными. Строка таблицы с
маркером столбца ``{{items.name}}`` повторяется на каждую позицию списка.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from io import BytesIO

from docx import Document as open_docx
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from core.domain.documents import (
    LEADING_SEPARATOR,
    MARKER,
    conditional_spans,
    marker_value,
    row_column,
    row_count,
    row_key,
    row_marker,
)
from core.domain.places import Place, place_spans
from core.files.errors import TemplateFileError

_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
# Куски текста абзаца: прямые и внутри ссылок, правок, полей и элементов управления.
_RUNS = (
    "./w:r | ./w:hyperlink/w:r | ./w:ins/w:r | ./w:smartTag/w:r | ./w:fldSimple/w:r"
    " | ./w:sdt/w:sdtContent/w:r | ./w:customXml/w:r"
)
_W_T, _W_TAB, _W_BR, _W_CR = qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")
_W_P, _W_TBL, _W_TR, _W_TC, _W_SDT = qn("w:p"), qn("w:tbl"), qn("w:tr"), qn("w:tc"), qn("w:sdt")
_XML_SPACE = qn("xml:space")
_NO_BORDER = frozenset({"nil", "none"})
# Ячейки строки таблицы в тексте для предпросмотра: «ИНН  7707083893  КПП  770701001».
CELL_GAP = "  "


def _open(data: bytes) -> DocxDocument:
    try:
        return open_docx(BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError, etree.XMLSyntaxError) as exc:
        raise TemplateFileError(f"DOCX не открылся: {exc}") from exc


def _roots(document: DocxDocument, *, all_parts: bool) -> list[etree._Element]:
    """Тело документа и колонтитулы: сверху шапка, снизу подвал.

    Для текста образца берутся колонтитулы разделов, для сборки — все части
    колонтитулов пакета: у первой страницы бывает своя шапка с реквизитами."""
    headers: list[etree._Element] = []
    footers: list[etree._Element] = []
    if all_parts:
        for part in document.part.package.iter_parts():
            name = str(part.partname)
            if name.startswith("/word/header"):
                headers.append(part.element)
            elif name.startswith("/word/footer"):
                footers.append(part.element)
    else:
        for section in document.sections:
            if not section.header.is_linked_to_previous:
                headers.append(section.header.part.element)
            if not section.footer.is_linked_to_previous:
                footers.append(section.footer.part.element)
    return [*headers, document.element.body, *footers]


def _paragraphs(root: etree._Element, *, with_fallback: bool) -> Iterator[etree._Element]:
    """Абзацы по порядку, включая таблицы и надписи. Запасная копия надписи
    (mc:Fallback) в текст образца не идёт — иначе строки задвоятся, — но при
    сборке заполняется тоже: какую копию покажет редактор, решает он."""
    for paragraph in root.iter(qn("w:p")):
        if with_fallback or next(paragraph.iterancestors(_MC_FALLBACK), None) is None:
            yield paragraph


def _nodes(paragraph: etree._Element) -> list[tuple[etree._Element, str]]:
    nodes: list[tuple[etree._Element, str]] = []
    for run in paragraph.xpath(_RUNS):
        for child in run:
            if child.tag == _W_T:
                nodes.append((child, child.text or ""))
            elif child.tag == _W_TAB:
                nodes.append((child, "\t"))
            elif child.tag in (_W_BR, _W_CR):
                nodes.append((child, "\n"))
    return nodes


def _text(paragraph: etree._Element) -> str:
    return "".join(text for _, text in _nodes(paragraph))


def _set_text(node: etree._Element, text: str) -> None:
    """Текст куска; перевод строки в значении — разрыв строки Word, а не пробел."""
    first, *rest = text.split("\n")
    node.text = first
    node.set(_XML_SPACE, "preserve")
    anchor = node
    for line in rest:
        br, t = OxmlElement("w:br"), OxmlElement("w:t")
        t.text = line
        t.set(_XML_SPACE, "preserve")
        anchor.addnext(br)
        br.addnext(t)
        anchor = t


def _replace(paragraph: etree._Element, begin: int, end: int, value: str) -> None:
    """Заменить отрезок текста абзаца: значение — в первый затронутый кусок,
    из остальных затронутых вырезается их часть, табуляции и разрывы внутри
    отрезка удаляются."""
    position = 0
    placed = False
    for node, text in _nodes(paragraph):
        start, stop = position, position + len(text)
        position = stop
        if stop <= begin or start >= end:
            continue
        if node.tag != _W_T:
            node.getparent().remove(node)
            continue
        head = text[: max(0, begin - start)]
        tail = text[end - start :] if stop > end else ""
        if placed:
            _set_text(node, head + tail)
        else:
            _set_text(node, head + value + tail)
            placed = True


def _own_line(paragraph: etree._Element) -> bool:
    """У абзаца своё место для значения: ячейка таблицы или линейка (нижняя
    граница абзаца). Так в бланках рисуют место для ручного заполнения вместо «______»."""
    cell = paragraph.getparent()
    if cell is not None and cell.tag == _W_TC:
        return True
    border = paragraph.find("./w:pPr/w:pBdr/w:bottom", paragraph.nsmap)
    return border is not None and border.get(qn("w:val")) not in _NO_BORDER


def _fill_paragraph(
    paragraph: etree._Element,
    places: Sequence[tuple[str, Place]],
    context: Mapping[str, str],
    blank: str,
) -> bool:
    """Заполнить абзац. ``True`` — абзац не печатать: выпал условный кусок,
    и значений в абзаце не осталось, только подпись."""
    for begin, end, key in reversed(place_spans(_text(paragraph), places)):
        _replace(paragraph, begin, end, "{{" + key + "}}")
    dropped = False
    for start, end, keep, opening in reversed(conditional_spans(_text(paragraph), context)):
        if keep:
            _replace(paragraph, end - 2, end, "")
            _replace(paragraph, start, start + opening, "")
        else:
            _replace(paragraph, start, end, "")
            dropped = True
    text = _text(paragraph)
    markers = list(MARKER.finditer(text))
    if dropped and not markers:
        return True
    if dropped and (separator := LEADING_SEPARATOR.match(text)) is not None:
        _replace(paragraph, separator.end(1), separator.end(), "")
        text = _text(paragraph)
        # «, тел. …» без первого куска — начало фразы: «Тел. …».
        first = separator.end(1)
        if first < len(text) and text[first].islower():
            _replace(paragraph, first, first + 1, text[first].upper())
            text = _text(paragraph)
        markers = list(MARKER.finditer(text))
    # Маркер — всё содержимое ячейки или линейки: пустое значение оставляет её
    # пустой, как в бланке. Прочерк поверх нарисованной линии задвоил бы её.
    if len(markers) == 1 and markers[0].group(0) == text.strip() and _own_line(paragraph):
        blank = ""
    for match in reversed(markers):
        _replace(paragraph, match.start(), match.end(), marker_value(match, context, blank))
    return False


def _drop_paragraph(paragraph: etree._Element) -> None:
    """Убрать абзац. Абзац со свойствами раздела, единственный в ячейке или
    надписи и последний в ячейке после вложенной таблицы только очищается:
    без него документ не откроется в Word."""
    parent = paragraph.getparent()
    siblings = parent.findall(_W_P)
    previous = paragraph.getprevious()
    keep = (
        paragraph.find("./w:pPr/w:sectPr", paragraph.nsmap) is not None
        or len(siblings) < 2
        or (
            parent.tag == _W_TC
            and paragraph.getnext() is None
            and previous is not None
            and previous.tag == _W_TBL
        )
    )
    if keep:
        _replace(paragraph, 0, len(_text(paragraph)), "")
    else:
        parent.remove(paragraph)


def _cells_text(cell: etree._Element) -> str:
    return "".join(_text(paragraph) for paragraph in cell.iter(_W_P))


_TC_PR_HEAD = frozenset({qn("w:cnfStyle"), qn("w:tcW"), qn("w:gridSpan"), qn("w:hMerge")})


def _set_vmerge(cell: etree._Element, *, restart: bool) -> None:
    """Объединить ячейку с соседней по вертикали. ``w:vMerge`` стоит в свойствах
    ячейки строго после ширины и объединения по горизонтали: Word проверяет
    порядок элементов и иначе считает файл повреждённым."""
    props = cell.find(qn("w:tcPr"))
    if props is None:
        props = OxmlElement("w:tcPr")
        cell.insert(0, props)
    for old in props.findall(qn("w:vMerge")):
        props.remove(old)
    merge = OxmlElement("w:vMerge")
    if restart:
        merge.set(qn("w:val"), "restart")
    position = 0
    for index, child in enumerate(props):
        if child.tag in _TC_PR_HEAD:
            position = index + 1
    props.insert(position, merge)


def _repeat_rows(root: etree._Element, context: Mapping[str, str]) -> None:
    """Строка позиций — копия на каждую позицию списка, маркеры столбцов в
    копии получают номер: ``{{items.name}}`` → ``{{items.2.name}}``. Строка —
    ближайшая строка таблицы, а вне таблицы — сам абзац. Ячейка со значением
    документа (срок поставки на весь заказ) объединяется по вертикали на все
    копии: иначе значение печаталось бы в каждой строке."""
    units: list[etree._Element] = []
    for paragraph in list(root.iter(_W_P)):
        if row_key(_text(paragraph)) is None:
            continue
        row = next(paragraph.iterancestors(_W_TR), None)
        unit = paragraph if row is None else row
        if not any(unit is seen for seen in units):
            units.append(unit)
    for unit in units:
        key = next(found for p in unit.iter(_W_P) if (found := row_key(_text(p))) is not None)
        count = row_count(context, key)
        shared = [
            cell
            for cell in (unit.findall(_W_TC) if unit.tag == _W_TR else [])
            if MARKER.search(_cells_text(cell)) and row_key(_cells_text(cell)) is None
        ]
        for index in range(1, count + 1):
            copy = deepcopy(unit)
            for paragraph in list(copy.iter(_W_P)):
                text = _text(paragraph)
                for match in reversed(list(MARKER.finditer(text))):
                    if row_column(match) is not None:
                        _replace(paragraph, match.start(), match.end(), row_marker(match, index))
                    elif index > 1 and row_key(text) is not None:
                        _replace(paragraph, match.start(), match.end(), "")
            if count > 1:
                for position in (unit.index(cell) for cell in shared):
                    cell = copy[position]
                    if index > 1:
                        for paragraph in cell.iter(_W_P):
                            _replace(paragraph, 0, len(_text(paragraph)), "")
                    _set_vmerge(cell, restart=index == 1)
            unit.addprevious(copy)
        unit.getparent().remove(unit)


def docx_lines(data: bytes) -> list[str]:
    """Текст образца: строка на абзац — шапка, тело с таблицами, подвал."""
    document = _open(data)
    return [
        _text(paragraph)
        for root in _roots(document, all_parts=False)
        for paragraph in _paragraphs(root, with_fallback=False)
    ]


def _join_cells(parts: Sequence[str]) -> str:
    """Ячейки строки таблицы через ``CELL_GAP``; кавычки и «20» + «26» в дате
    бланка («___» ______ 20__ г.) — без зазора, как они стоят на листе."""
    out, last = "", ""
    for part in (part.strip() for part in parts):
        if not part:
            continue
        tight = (
            out.endswith(("«", "(")) or part.startswith(("»", ")", "!", ",", ".")) or last == "20"
        )
        out += part if not out or tight else CELL_GAP + part
        last = part
    return out


def _table_lines(table: etree._Element) -> list[str]:
    """Строка таблицы — строки текста: абзацы ячеек идут рядом, как на листе,
    — первый абзац каждой ячейки в одной строке, второй — в следующей."""
    lines: list[str] = []
    for row in table.iter(_W_TR):
        if next(row.iterancestors(_W_TBL)) is not table:
            continue
        cells = [
            [line for line in _block_lines(cell) if line.strip()] for cell in row.findall(_W_TC)
        ]
        depth = max((len(cell) for cell in cells), default=0)
        if depth == 0:
            lines.append("")
        lines.extend(
            _join_cells([cell[index] if index < len(cell) else "" for cell in cells])
            for index in range(depth)
        )
    return lines


def _block_lines(container: etree._Element) -> list[str]:
    """Строки для предпросмотра по порядку блоков: абзац — строка, строка
    таблицы — её ячейки рядом. Надписи внутри абзаца — после него."""
    lines: list[str] = []
    for child in container:
        if child.tag == _W_P:
            lines.append(_text(child))
            lines.extend(
                _text(inner)
                for inner in child.iter(_W_P)
                if inner is not child and next(inner.iterancestors(_MC_FALLBACK), None) is None
            )
        elif child.tag == _W_TBL:
            lines.extend(_table_lines(child))
        elif child.tag == _W_SDT:
            content = child.find("./w:sdtContent", child.nsmap)
            if content is not None:
                lines.extend(_block_lines(content))
    return lines


def docx_layout(data: bytes) -> list[str]:
    """Текст образца для предпросмотра: как ``docx_lines``, но строка таблицы —
    одна строка текста, а не столбик ячеек. Места полей в нём ищутся так же:
    каждая строка ``docx_lines`` целиком входит в какую-то строку раскладки."""
    document = _open(data)
    return [line for root in _roots(document, all_parts=False) for line in _block_lines(root)]


_CELL_LABEL_MAX = 60
_LABEL_LETTERS = re.compile(r"[А-Яа-яЁёA-Za-z]{2,}")


def _grid(row: etree._Element) -> list[tuple[int, etree._Element]]:
    """Ячейки строки с номером первой колонки сетки: подпись под ячейкой ищется
    в следующей строке по той же колонке, а ячейки бывают объединены."""
    cells: list[tuple[int, etree._Element]] = []
    column = 0
    for cell in row.findall(_W_TC):
        cells.append((column, cell))
        span = cell.find("./w:tcPr/w:gridSpan", cell.nsmap)
        column += int(span.get(qn("w:val"), "1")) if span is not None else 1
    return cells


def _plain(cell: etree._Element) -> str:
    return " ".join(_text(p).strip() for p in cell.iter(_W_P) if _text(p).strip())


def _cell_label(left: str, caption: str) -> str:
    """Название места по подписи слева («ИНН») и подстрочнику под ним («цифрами»)."""
    parts = [
        re.sub(r"\s+", " ", text).strip(" :—–-").replace("{", "").replace("}", "")
        for text in (left, caption)
    ]
    left, caption = (part if _LABEL_LETTERS.search(part) else "" for part in parts)
    label = f"{left} ({caption})" if left and caption else left or caption
    if len(label) > _CELL_LABEL_MAX:
        label = label[:_CELL_LABEL_MAX].rsplit(" ", 1)[0]
    return label[:1].upper() + label[1:]


def mark_blank_cells(data: bytes) -> bytes | None:
    """Бланк, где место для данных — пустая ячейка с линейкой снизу («ИНН
    ______» таблицей): вписать в такие ячейки метки ``{{Подпись}}`` по подписи
    слева и подстрочнику снизу. Текст пустой ячейки не на что сослаться как на
    место, а метку видно и человеку, и разбору; пустое значение потом снова
    даёт пустую ячейку. ``None`` — размечать нечего, файл остаётся как был."""
    document = _open(data)
    marked = 0
    for root in _roots(document, all_parts=False):
        for table in root.iter(_W_TBL):
            rows = [_grid(row) for row in table.findall(_W_TR)]
            for index, cells in enumerate(rows):
                below = dict(rows[index + 1]) if index + 1 < len(rows) else {}
                for position, (column, cell) in enumerate(cells):
                    paragraphs = cell.findall(_W_P)
                    if (
                        len(paragraphs) != 1
                        or _plain(cell)
                        or cell.find(_W_TBL) is not None
                        or not _own_line(paragraphs[0])
                        or not _bottom_border(cell)
                    ):
                        continue
                    left = _plain(cells[position - 1][1]) if position > 0 else ""
                    caption_cell = below.get(column)
                    caption = _plain(caption_cell) if caption_cell is not None else ""
                    label = _cell_label(left, caption)
                    if not label:
                        continue
                    source = cells[position - 1][1] if position > 0 else None
                    _put_marker(paragraphs[0], "{{" + label + "}}", source)
                    marked += 1
    if not marked:
        return None
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _bottom_border(cell: etree._Element) -> bool:
    border = cell.find("./w:tcPr/w:tcBorders/w:bottom", cell.nsmap)
    return border is not None and border.get(qn("w:val")) not in _NO_BORDER


def _put_marker(paragraph: etree._Element, text: str, source: etree._Element | None) -> None:
    """Кусок текста с оформлением подписи рядом: значение встанет тем же шрифтом."""
    run = OxmlElement("w:r")
    style = source.find(".//w:r/w:rPr", source.nsmap) if source is not None else None
    if style is not None:
        run.append(deepcopy(style))
    node = OxmlElement("w:t")
    node.text = text
    node.set(_XML_SPACE, "preserve")
    run.append(node)
    paragraph.append(run)


def fill_docx(
    data: bytes,
    *,
    places: Sequence[tuple[str, Place]],
    context: Mapping[str, str],
    blank: str,
) -> bytes:
    """Документ в оформлении образца: места и маркеры ``{{key}}`` → значения.
    Пустое значение печатается ``blank`` — как в текстовом шаблоне, — кроме
    необязательного в условном куске ``[[…]]``: оно исчезает с подписью."""
    document = _open(data)
    for root in _roots(document, all_parts=True):
        _repeat_rows(root, context)
        # Ячейки с данными каждой строки, где есть условный кусок: строка
        # уходит, когда опустели все они, а подписи вроде «Адрес» остались одни.
        data_cells = {
            row: [cell for cell in row.findall(_W_TC) if "{{" in _cells_text(cell)]
            for row in root.iter(_W_TR)
            if "[[" in _cells_text(row)
        }
        collapsed: list[etree._Element] = []
        for paragraph in list(_paragraphs(root, with_fallback=True)):
            if _fill_paragraph(paragraph, places, context, blank):
                row = next(paragraph.iterancestors(_W_TR), None)
                if row is not None and not any(row is seen for seen in collapsed):
                    collapsed.append(row)
                _drop_paragraph(paragraph)
        for row in collapsed:
            cells = data_cells.get(row, [])
            merged = row.find(".//w:vMerge", row.nsmap) is not None
            table = row.getparent()
            if (
                cells
                and not merged
                and len(table.findall(_W_TR)) > 1
                and not any(_cells_text(cell).strip() for cell in cells)
            ):
                table.remove(row)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
