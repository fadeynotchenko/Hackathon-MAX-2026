"""HTTP-контракт своих шаблонов: сохранить, взять в работу, изменить, удалить."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.usecases.documents import ensure_builtin_templates
from tests.api.test_documents_api import _auth
from tests.samples import offer_docx

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ACT = {
    "title": "Акт выполненных работ",
    "description": "К договору услуг",
    "body": "Акт от {{date}}\nЗаказчик: {{client_name}}\nРаботы: {{works}}",
    "fields": [
        {"key": "date", "label": "Дата акта", "type": "date", "today_by_default": True},
        {"key": "client_name", "label": "Название клиента"},
        {"key": "works", "label": "Работы", "type": "multiline"},
    ],
}


async def test_own_template_round_trip(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    headers = await _auth(client, make_init_data)

    created = await client.post("/api/v1/templates", headers=headers, json=ACT)
    assert created.status_code == 201, created.text
    template = created.json()
    assert (template["kind"], template["is_builtin"]) == ("custom", False)
    assert template["body"] == ACT["body"]
    assert template["preview"].startswith("Акт от __________")
    date = next(f for f in template["fields"] if f["key"] == "date")
    assert date["today_by_default"] is True and date["group"] == "Предмет"

    library = (await client.get("/api/v1/templates", headers=headers)).json()
    assert template["id"] in {item["id"] for item in library}

    document = await client.post(
        "/api/v1/documents", headers=headers, json={"template_id": template["id"]}
    )
    assert document.status_code == 201, document.text
    assert document.json()["title"] == "Акт выполненных работ"

    edited = await client.put(
        f"/api/v1/templates/{template['id']}",
        headers=headers,
        json=ACT | {"title": "Акт сдачи-приёмки"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["id"] == template["id"]
    kept = await client.get(f"/api/v1/documents/{document.json()['id']}", headers=headers)
    assert kept.json()["template"]["title"] == "Акт выполненных работ"

    deleted = await client.delete(f"/api/v1/templates/{template['id']}", headers=headers)
    assert deleted.status_code == 200
    gone = await client.get(f"/api/v1/templates/{template['id']}", headers=headers)
    assert gone.status_code == 404
    still = await client.get(f"/api/v1/documents/{document.json()['id']}", headers=headers)
    assert still.status_code == 200


async def test_template_errors_are_readable(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    headers = await _auth(client, make_init_data)

    invalid = await client.post(
        "/api/v1/templates", headers=headers, json=ACT | {"body": "Акт {{date}}"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "template.invalid"
    assert "«Работы» не встречается в тексте" in invalid.json()["detail"]

    (invoice,) = (await client.get("/api/v1/templates?slug=invoice", headers=headers)).json()
    builtin = await client.put(f"/api/v1/templates/{invoice['id']}", headers=headers, json=ACT)
    assert builtin.status_code == 403
    assert builtin.json()["code"] == "template.builtin"

    created = (await client.post("/api/v1/templates", headers=headers, json=ACT)).json()
    stranger = await _auth(client, make_init_data, user_id=2)
    foreign = await client.delete(f"/api/v1/templates/{created['id']}", headers=stranger)
    assert foreign.status_code == 404


async def test_template_from_sample_file(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    headers = await _auth(client, make_init_data)

    imported = await client.post(
        "/api/v1/templates/import?filename=КП.docx",
        headers=headers | {"Content-Type": DOCX_TYPE},
        content=offer_docx(marked=True),
    )
    assert imported.status_code == 200, imported.text
    draft = imported.json()
    assert (draft["format"], draft["found_by"]) == ("docx", "markers")
    assert [field["label"] for field in draft["fields"]] == ["Название клиента", "Сумма"]

    created = await client.post(
        "/api/v1/templates",
        headers=headers,
        json={
            "title": draft["title"],
            "file_id": draft["file_id"],
            "fields": [
                {
                    "key": "client_name",
                    "label": "Название клиента",
                    "places": draft["fields"][0]["places"],
                },
                {
                    "key": "total",
                    "label": "Сумма",
                    "type": "money",
                    "places": draft["fields"][1]["places"],
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    template = created.json()
    assert template["file"] == {"id": draft["file_id"], "filename": "КП.docx", "text": None}
    assert "Для: {{client_name}}" in template["body"]
    one = (await client.get(f"/api/v1/templates/{template['id']}", headers=headers)).json()
    assert one["file"]["text"] == draft["text"]
    assert one["fields"][0]["places"] == [{"text": "{{ Название клиента }}", "before": ""}]

    unsupported = await client.post(
        "/api/v1/templates/import", headers=headers, content=b"just text"
    )
    assert unsupported.status_code == 415
