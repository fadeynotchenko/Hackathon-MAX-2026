"""Подпись и печать картинками: подготовка к вставке в документ.

Подпись и печать обычно фотографируют на белом листе. Белый фон делается
прозрачным — иначе белый прямоугольник закрыл бы линию подписи и текст под
печатью, — и картинка уменьшается: в документе она размером со штамп, а
фото с телефона весит мегабайты и раздувало бы каждый файл.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from core.files.errors import TemplateFileError

# Сторона картинки после уменьшения: печать в документе ~4 см, это ~470 точек
# при 300 dpi, запас — на чёткость при печати.
MARK_MAX_SIDE = 800
# Светлее этого пиксель считается фоном листа.
_WHITE = 225


class MarkImageError(TemplateFileError):
    """Картинка подписи или печати не открылась."""


def prepare_mark(data: bytes) -> bytes:
    """PNG с прозрачным фоном не больше ``MARK_MAX_SIDE`` по большей стороне."""
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MarkImageError(f"картинка не открылась: {exc}") from exc
    image = image.convert("RGBA")
    image.thumbnail((MARK_MAX_SIDE, MARK_MAX_SIDE))
    pixels = [
        (r, g, b, 0) if min(r, g, b) >= _WHITE else (r, g, b, a) for r, g, b, a in image.getdata()
    ]
    image.putdata(pixels)
    bbox = image.getbbox()
    if bbox is None:
        raise MarkImageError("на картинке только белый фон")
    out = BytesIO()
    image.crop(bbox).save(out, format="PNG", optimize=True)
    return out.getvalue()
