"""Подпись и печать: прозрачный фон, размер штампа, место в строке подписи."""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document
from PIL import Image, ImageDraw

from core.files import MarkImageError, Marks, docx_lines, fill_docx, prepare_mark
from core.usecases.documents.builtin import BUILTIN_TEMPLATES, INVOICE

_ANCHOR = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}anchor"


def photo(size: tuple[int, int] = (2400, 1200)) -> bytes:
    """Печать, снятая телефоном на белом листе."""
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).ellipse((300, 100, 2100, 1100), outline=(20, 40, 160), width=40)
    out = BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


def test_mark_gets_transparent_background_and_stamp_size() -> None:
    prepared = Image.open(BytesIO(prepare_mark(photo())))
    assert prepared.format == "PNG" and prepared.mode == "RGBA"
    assert max(prepared.size) <= 800, "фото с телефона уменьшается"
    assert prepared.getpixel((prepared.width // 2, prepared.height // 2))[3] == 0, "фон прозрачный"


def test_blank_or_broken_picture_is_refused() -> None:
    with pytest.raises(MarkImageError):
        prepare_mark(b"not an image")
    white = BytesIO()
    Image.new("RGB", (100, 100), "white").save(white, format="PNG")
    with pytest.raises(MarkImageError):
        prepare_mark(white.getvalue())


def _anchors(data: bytes) -> int:
    return sum(1 for _ in Document(BytesIO(data)).element.body.iter(_ANCHOR))


# У сторон-граждан нет строки подписи продавца с должностным лицом: подпись и
# печать туда не ставятся.
_WITHOUT_SIGN_LINE = {"contract-persons", "contract-self-employed", "act-transfer"}


def test_marks_go_into_the_seller_sign_line_of_every_blank_that_has_one() -> None:
    mark = prepare_mark(photo())
    for template in BUILTIN_TEMPLATES:
        signed = fill_docx(
            template.blank_bytes(),
            places=(),
            context={"seller_director": "Иванов И. И."},
            blank="____",
            marks=Marks(signature=mark, stamp=mark),
        )
        assert (_anchors(signed) > 0) == (template.slug not in _WITHOUT_SIGN_LINE), template.slug


def test_name_in_the_header_is_not_a_sign_line() -> None:
    """В шапке акта «директор Иванов И. И.» — не место подписи: подпись и печать
    встают один раз, в строку «Исполнитель: ______ / Иванов И. И.»."""
    act = next(t for t in BUILTIN_TEMPLATES if t.slug == "act-services")
    mark = prepare_mark(photo())
    signed = fill_docx(
        act.blank_bytes(),
        places=(),
        context={"seller_director": "Иванов И. И."},
        blank="____",
        marks=Marks(signature=mark, stamp=mark),
    )
    assert _anchors(signed) == 2


def test_text_of_the_document_stays_the_same_with_marks() -> None:
    mark = prepare_mark(photo())
    context = {"seller_director": "Иванов И. И.", "seller_name": "ООО «Ромашка»"}
    plain = fill_docx(INVOICE.blank_bytes(), places=(), context=context, blank="____")
    signed = fill_docx(
        INVOICE.blank_bytes(), places=(), context=context, blank="____", marks=Marks(stamp=mark)
    )
    assert docx_lines(signed) == docx_lines(plain), "картинка не сдвигает и не меняет текст"
    assert _anchors(signed) == 1 and _anchors(plain) == 0
