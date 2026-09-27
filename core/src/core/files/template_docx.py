"""Шаблон-файл DOCX: текст образца и сборка документа в его оформлении.

Документ по такому шаблону собирается не заново, а в копии файла компании:
логотип, шрифты, таблицы и колонтитулы остаются как были, меняются только
места для данных. Word режет текст абзаца на куски (runs) по своему усмотрению —
«ООО «Альфа»» легко оказывается в трёх кусках с разным оформлением, — поэтому
места ищутся в тексте абзаца целиком, а замена правит только затронутые куски:
значение встаёт в первый из них и берёт его оформление.

Сборка идёт в два прохода: места → маркеры ``{{key}}``, маркеры → значения.
Иначе значение одного поля, похожее на место другого, заменилось бы повторно.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from io import BytesIO

from docx import Document as open_docx
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from core.domain.places import Place, place_spans
from core.files.errors import TemplateFileError

_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
# Куски текста абзаца: прямые и внутри ссылок, правок, полей и элементов управления.
_RUNS = (
    "./w:r | ./w:hyperlink/w:r | ./w:ins/w:r | ./w:smartTag/w:r | ./w:fldSimple/w:r"
    " | ./w:sdt/w:sdtContent/w:r | ./w:customXml/w:r"
)
_W_T, _W_TAB, _W_BR, _W_CR = qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")
_XML_SPACE = qn("xml:space")
_KEY_MARKER = re.compile(r"{{\s*(\w+)\s*}}")


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


def _fill_paragraph(
    paragraph: etree._Element,
    places: Sequence[tuple[str, Place]],
    context: Mapping[str, str],
    blank: str,
) -> None:
    for begin, end, key in reversed(place_spans(_text(paragraph), places)):
        _replace(paragraph, begin, end, "{{" + key + "}}")
    markers = list(_KEY_MARKER.finditer(_text(paragraph)))
    for match in reversed(markers):
        _replace(paragraph, match.start(), match.end(), context.get(match.group(1)) or blank)


def docx_lines(data: bytes) -> list[str]:
    """Текст образца: строка на абзац — шапка, тело с таблицами, подвал."""
    document = _open(data)
    return [
        _text(paragraph)
        for root in _roots(document, all_parts=False)
        for paragraph in _paragraphs(root, with_fallback=False)
    ]


def fill_docx(
    data: bytes,
    *,
    places: Sequence[tuple[str, Place]],
    context: Mapping[str, str],
    blank: str,
) -> bytes:
    """Документ в оформлении образца: места и маркеры ``{{key}}`` → значения.
    Пустое значение печатается ``blank`` — как в текстовом шаблоне."""
    document = _open(data)
    for root in _roots(document, all_parts=True):
        for paragraph in _paragraphs(root, with_fallback=True):
            _fill_paragraph(paragraph, places, context, blank)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
