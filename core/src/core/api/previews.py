"""Ответ с картинкой страницы для ручек предпросмотра шаблона и документа и
прогрев листа после правки документа.

Число страниц — в заголовке: мини-апп грузит первую страницу и по нему решает,
сколько ещё показывать, без отдельного запроса. Картинка приватная (за Bearer),
но редакция в ней неизменна — её ключ содержимое, поэтому клиенту можно держать
её в кеше.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import BackgroundTasks, Query, Response

from core.api.schemas.common import ErrorResponse
from core.db import get_session
from core.files import PREVIEW_WIDTHS, FilesConfig, PreviewPage
from core.logs import biz_warn
from core.usecases.documents import blank_source, document_source, preview_page

logger = logging.getLogger(__name__)

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
            # Мини-апп кладёт версию документа в адрес (?v=), поэтому один адрес —
            # одна редакция навсегда, и повторный показ берётся из кеша телефона.
            "Cache-Control": "private, max-age=31536000, immutable",
        },
    )


async def _warm(user_id: int, document_id: int, cfg: FilesConfig) -> None:
    try:
        # Документ читается короткой сессией, лист рисуется уже без неё.
        async with get_session() as session:
            source = await document_source(session, user_id=user_id, document_id=document_id)
        await preview_page(source, page=1, size="page", cfg=cfg)
    except Exception as exc:
        # Прогрев — ускорение, а не условие: лист нарисуется по запросу.
        biz_warn(logger, "previews.document_warm_failed", document_id=document_id, error=str(exc))


def warm_document(
    background: BackgroundTasks, *, user_id: int, document_id: int, cfg: FilesConfig
) -> None:
    """Нарисовать лист документа сразу после правки, в фоне после ответа.

    LibreOffice тратит на лист секунды; если начинать по запросу картинки,
    человек на экране проверки ждёт их. После правки до экрана проверки
    проходит как раз столько, сколько нужно, чтобы лист был готов."""
    background.add_task(_warm, user_id, document_id, cfg)


async def _warm_template(user_id: int, template_id: int, cfg: FilesConfig) -> None:
    try:
        async with get_session() as session:
            source = await blank_source(session, user_id=user_id, template_id=template_id)
        for size in PREVIEW_WIDTHS:
            await preview_page(source, page=1, size=size, cfg=cfg)
    except Exception as exc:
        biz_warn(logger, "previews.template_warm_failed", template_id=template_id, error=str(exc))


def warm_template(
    background: BackgroundTasks, *, user_id: int, template_id: int, cfg: FilesConfig
) -> None:
    """Свой шаблон рисуется сразу после сохранения: в каталоге его карточка и
    экран шаблона открываются с готовым листом, как у стандартных."""
    background.add_task(_warm_template, user_id, template_id, cfg)
