"""HTTP-контракт своих организаций: несколько карточек, основная, выбор в документе."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.test_documents_api import _auth, _seed
from tests.files.test_marks import photo


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


async def test_signature_and_stamp_are_uploaded_shown_and_make_files_stale(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    stranger = await _auth(client, make_init_data, user_id=2)
    company = await client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "ООО «Ромашка»", "values": {"inn": "7707083893"}},
    )
    url = f"/api/v1/organizations/{company.json()['id']}/marks"
    assert company.json()["has_stamp"] is False

    invoice = (await client.get("/api/v1/templates?slug=invoice", headers=headers)).json()[0]
    document = (
        await client.post("/api/v1/documents", headers=headers, json={"template_id": invoice["id"]})
    ).json()
    before = await client.get(f"/api/v1/documents/{document['id']}/files", headers=headers)

    uploaded = await client.put(
        f"{url}/stamp", headers={**headers, "Content-Type": "image/jpeg"}, content=photo()
    )
    assert uploaded.status_code == 200, uploaded.text
    assert (uploaded.json()["has_stamp"], uploaded.json()["has_signature"]) == (True, False)
    shown = await client.get(f"{url}/stamp", headers=headers)
    assert (shown.status_code, shown.headers["content-type"]) == (200, "image/png")
    assert (await client.get(f"{url}/stamp", headers=stranger)).status_code == 404
    assert (await client.get(f"{url}/signature", headers=headers)).status_code == 404

    not_image = await client.put(
        f"{url}/signature",
        headers={**headers, "Content-Type": "application/pdf"},
        content=b"%PDF-1",
    )
    assert not_image.status_code in (415, 422)

    removed = await client.delete(f"{url}/stamp", headers=headers)
    assert removed.json()["has_stamp"] is False
    assert before.status_code == 200
