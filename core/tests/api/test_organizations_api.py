"""HTTP-контракт своих организаций: несколько карточек, основная, выбор в документе."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.test_documents_api import _auth, _seed


async def test_organizations_crud_and_document_from_chosen_one(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    url = "/api/v1/organizations"

    first = await client.post(
        url, headers=headers, json={"name": "ООО «Ромашка»", "values": {"inn": "7707083893"}}
    )
    second = await client.post(
        url, headers=headers, json={"name": "ИП Нотченко", "values": {"inn": "500100732259"}}
    )
    assert first.status_code == second.status_code == 201, second.text
    assert (first.json()["is_default"], second.json()["is_default"]) == (True, False)

    bad = await client.post(url, headers=headers, json={"name": "Кривая", "values": {"inn": "123"}})
    assert bad.status_code == 422 and bad.json()["code"] == "organization.invalid"

    ip_id = second.json()["id"]
    moved = await client.put(
        f"{url}/{ip_id}",
        headers=headers,
        json={"name": "ИП Нотченко Ф. В.", "values": {"inn": "500100732259"}, "is_default": True},
    )
    assert moved.status_code == 200 and moved.json()["is_default"] is True
    listed = (await client.get(url, headers=headers)).json()
    assert [o["name"] for o in listed] == ["ИП Нотченко Ф. В.", "ООО «Ромашка»"]

    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    invoice_id = next(t["id"] for t in templates if t["slug"] == "invoice")
    created = await client.post(
        "/api/v1/documents",
        headers=headers,
        json={"template_id": invoice_id, "organization_id": first.json()["id"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["organization_id"] == first.json()["id"]
    assert created.json()["values"]["seller_name"]["value"] == "ООО «Ромашка»"

    other = await _auth(client, make_init_data, user_id=2)
    foreign = await client.delete(f"{url}/{ip_id}", headers=other)
    assert foreign.status_code == 404, "чужую организацию не удалить"
    gone = await client.delete(f"{url}/{ip_id}", headers=headers)
    assert gone.status_code == 200
    (left,) = (await client.get(url, headers=headers)).json()
    assert left["name"] == "ООО «Ромашка»" and left["is_default"] is True
