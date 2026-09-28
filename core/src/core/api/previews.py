"""Ответ с картинкой страницы для ручек предпросмотра шаблона и документа.

Число страниц — в заголовке: мини-апп грузит первую страницу и по нему решает,
сколько ещё показывать, без отдельного запроса. Картинка приватная (за Bearer),
но редакция в ней неизменна — её ключ содержимое, поэтому клиенту можно держать
её в кеше.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Query, Response

from core.api.schemas.common import ErrorResponse
from core.files import PreviewPage

PAGE_COUNT_HEADER = "X-Page-Count"

PreviewSize = Literal["thumb", "page"]
PageQuery = Query(1, ge=1, le=200, description="Номер страницы с единицы")
SizeQuery = Query("page", description="thumb — карточка каталога, page — лист во весь экран")

PREVIEW_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "content": {"image/jpeg": {}},
        "description": f"Страница JPEG; число страниц — в {PAGE_COUNT_HEADER}",
    },
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def preview_response(found: PreviewPage) -> Response:
    return Response(
        content=found.data,
        media_type="image/jpeg",
        headers={
            PAGE_COUNT_HEADER: str(found.pages),
            "Cache-Control": "private, max-age=600",
        },
    )
