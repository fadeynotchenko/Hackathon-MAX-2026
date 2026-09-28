"""Ручки предпросмотра листами отдают JPEG и число страниц в заголовке."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.files import previews as file_previews
from core.usecases.documents import previews
from tests.api.test_documents_api import _auth, _seed


async def test_template_preview_is_a_jpeg_page(
    client: AsyncClient,
    session: AsyncSession,
    make_init_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def to_pdf(docx: bytes, **_: object) -> bytes:
        return b"%PDF"

    async def to_jpeg(pdf: bytes, *, width: int, timeout_seconds: int) -> list[bytes]:
        return [b"\xff\xd8page-1", b"\xff\xd8page-2", b"\xff\xd8page-3"]

    monkeypatch.setattr(previews, "convert_to_pdf", to_pdf)
    monkeypatch.setattr(file_previews, "pdf_to_jpeg", to_jpeg)
    await _seed(session)
    headers = await _auth(client, make_init_data)
    templates = (await client.get("/api/v1/templates", headers=headers)).json()

    response = await client.get(
        f"/api/v1/templates/{templates[0]['id']}/preview",
        headers=headers,
        params={"page": 2, "size": "thumb"},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-page-count"] == "3"
    assert response.content == b"\xff\xd8page-2"
    missing = await client.get(
        f"/api/v1/templates/{templates[0]['id']}/preview", headers=headers, params={"page": 9}
    )
    assert missing.json()["code"] == "preview.page_not_found"
