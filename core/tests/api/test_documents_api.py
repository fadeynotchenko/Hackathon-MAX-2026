"""HTTP-контракт документов: библиотека, справочники, заполнение, история."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.events import DocumentReady
from core.usecases.documents import ensure_builtin_templates


async def _auth(client: AsyncClient, make_init_data, user_id: int = 1) -> dict[str, str]:
    response = await client.post("/api/v1/auth/max", json={"init_data": make_init_data(user_id)})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seed(session: AsyncSession) -> None:
    await ensure_builtin_templates(session)
    await session.commit()


async def test_templates_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/templates")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.missing_token"


async def test_template_library_lists_builtin(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    response = await client.get("/api/v1/templates", headers=headers)
    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()}
    assert slugs == {"invoice", "offer", "service-contract"}
    invoice = next(item for item in response.json() if item["slug"] == "invoice")
    assert invoice["is_builtin"] is True
    field = next(f for f in invoice["fields"] if f["key"] == "seller_inn")
    assert field["type"] == "inn" and field["required"] is True and field["group"]
    # Предпросмотр шаблона — тот же текст, что уйдёт в файл, только с пустыми местами.
    assert invoice["preview"].startswith("Счёт на оплату")
    assert "{{" not in invoice["preview"] and "__________" in invoice["preview"]


async def test_document_flow_from_requisites_to_preview(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)

    company = await client.post(
        "/api/v1/organizations",
        headers=headers,
        json={
            "name": "ООО «Ромашка»",
            "values": {
                "inn": "7707083893",
                "bank": "ПАО Сбербанк",
                "bic": "044525225",
                "account": "40702810438000123459",
            },
        },
    )
    assert company.status_code == 201, company.text
    assert company.json()["is_default"] is True, "первая организация — основная"

    client_card = await client.post(
        "/api/v1/counterparties",
        headers=headers,
        json={"name": "ООО «Клиент»", "values": {"inn": "500100732259"}},
    )
    assert client_card.status_code == 201, client_card.text

    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    invoice_id = next(t["id"] for t in templates if t["slug"] == "invoice")

    created = await client.post(
        "/api/v1/documents",
        headers=headers,
        json={"template_id": invoice_id, "counterparty_id": client_card.json()["id"]},
    )
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["status"] == "draft"
    assert document["values"]["seller_inn"]["source"] == "profile"
    assert document["values"]["client_name"]["source"] == "counterparty"
    assert "number" in document["missing"]

    filled = await client.patch(
        f"/api/v1/documents/{document['id']}/fields",
        headers=headers,
        json={
            "values": {
                "number": {"value": "17"},
                "date": {"value": "23.09.2026"},
                "item": {"value": "Разработка мини-приложения MAX"},
                "total": {"value": "450 000"},
            },
            "title": "Счёт № 17",
        },
    )
    assert filled.status_code == 200, filled.text
    body = filled.json()
    assert body["ready"] is True and body["status"] == "ready"
    assert body["title"] == "Счёт № 17"
    assert "450 000,00" in body["preview"]
    assert "ПАО Сбербанк" in body["preview"]

    history = await client.get("/api/v1/documents", headers=headers)
    assert [item["title"] for item in history.json()] == ["Счёт № 17"]
    assert history.json()[0]["counterparty_name"] == "ООО «Клиент»"


async def test_bad_field_value_is_explained(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    offer_id = next(t["id"] for t in templates if t["slug"] == "offer")
    document = (
        await client.post("/api/v1/documents", headers=headers, json={"template_id": offer_id})
    ).json()

    response = await client.patch(
        f"/api/v1/documents/{document['id']}/fields",
        headers=headers,
        json={"values": {"total": {"value": "договоримся"}}},
    )
    assert response.status_code == 200
    body = response.json()
    assert [e["code"] for e in body["errors"]] == ["field.money_invalid"]
    assert body["ready"] is False
    assert "total" not in body["values"]


async def test_recognized_value_waits_for_confirmation(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    offer_id = next(t["id"] for t in templates if t["slug"] == "offer")
    document = (
        await client.post("/api/v1/documents", headers=headers, json={"template_id": offer_id})
    ).json()

    response = await client.patch(
        f"/api/v1/documents/{document['id']}/fields",
        headers=headers,
        json={
            "values": {
                "client_name": {
                    "value": "ООО «Клиент»",
                    "source": "ocr",
                    "confidence": 0.71,
                    "confirmed": False,
                }
            }
        },
    )
    body = response.json()
    assert body["unconfirmed"] == ["client_name"]
    assert body["values"]["client_name"]["confidence"] == 0.71
    assert body["ready"] is False


async def test_documents_are_not_visible_to_other_users(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    owner = await _auth(client, make_init_data, user_id=1)
    templates = (await client.get("/api/v1/templates", headers=owner)).json()
    offer_id = next(t["id"] for t in templates if t["slug"] == "offer")
    document = (
        await client.post("/api/v1/documents", headers=owner, json={"template_id": offer_id})
    ).json()

    stranger = await _auth(client, make_init_data, user_id=2)
    response = await client.get(f"/api/v1/documents/{document['id']}", headers=stranger)
    assert response.status_code == 404
    assert response.json()["code"] == "document.not_found"


async def test_counterparty_with_bad_inn_is_rejected(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    headers = await _auth(client, make_init_data)
    response = await client.post(
        "/api/v1/counterparties",
        headers=headers,
        json={"name": "ООО «Опечатка»", "values": {"inn": "1234567890"}},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "counterparty.invalid"


async def test_render_and_download_over_http(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    offer_id = next(t["id"] for t in templates if t["slug"] == "offer")
    document = (
        await client.post("/api/v1/documents", headers=headers, json={"template_id": offer_id})
    ).json()

    not_ready = await client.post(
        f"/api/v1/documents/{document['id']}/render", headers=headers, json={"format": "docx"}
    )
    assert not_ready.status_code == 409
    assert not_ready.json()["code"] == "document.not_ready"

    await client.patch(
        f"/api/v1/documents/{document['id']}/fields",
        headers=headers,
        json={
            "values": {
                "date": {"value": "23.09.2026"},
                "seller_name": {"value": "ООО «Ромашка»"},
                "client_name": {"value": "ООО «Клиент»"},
                "subject": {"value": "Разработка"},
                "scope": {"value": "Бэкенд и бот"},
                "total": {"value": "450 000"},
                "valid_until": {"value": "31.10.2026"},
            },
            "title": "КП для Клиента",
        },
    )

    rendered = await client.post(
        f"/api/v1/documents/{document['id']}/render", headers=headers, json={"format": "docx"}
    )
    assert rendered.status_code == 200, rendered.text
    assert rendered.json()["filename"] == "КП для Клиента.docx"
    assert rendered.json()["stale"] is False

    listed = await client.get(f"/api/v1/documents/{document['id']}/files", headers=headers)
    assert [f["format"] for f in listed.json()] == ["docx"]

    downloaded = await client.get(
        f"/api/v1/documents/{document['id']}/file?format=docx", headers=headers
    )
    assert downloaded.status_code == 200
    assert downloaded.content[:2] == b"PK"
    assert "filename*=UTF-8''" in downloaded.headers["content-disposition"]
    assert downloaded.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )


async def test_other_user_cannot_download_file(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    owner = await _auth(client, make_init_data, user_id=1)
    templates = (await client.get("/api/v1/templates", headers=owner)).json()
    offer_id = next(t["id"] for t in templates if t["slug"] == "offer")
    document = (
        await client.post("/api/v1/documents", headers=owner, json={"template_id": offer_id})
    ).json()

    stranger = await _auth(client, make_init_data, user_id=2)
    response = await client.get(
        f"/api/v1/documents/{document['id']}/file?format=docx", headers=stranger
    )
    assert response.status_code == 404
    assert response.json()["code"] == "document.not_found"


async def test_send_publishes_event_and_token_works_once(
    client: AsyncClient, session: AsyncSession, redis, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    offer_id = next(t["id"] for t in templates if t["slug"] == "offer")
    document = (
        await client.post("/api/v1/documents", headers=headers, json={"template_id": offer_id})
    ).json()
    await client.patch(
        f"/api/v1/documents/{document['id']}/fields",
        headers=headers,
        json={
            "values": {
                "date": {"value": "23.09.2026"},
                "seller_name": {"value": "ООО «Ромашка»"},
                "client_name": {"value": "ООО «Клиент»"},
                "subject": {"value": "Разработка"},
                "scope": {"value": "Бэкенд и бот"},
                "total": {"value": "450 000"},
                "valid_until": {"value": "31.10.2026"},
            },
            "title": "КП для Клиента",
        },
    )

    sent = await client.post(
        f"/api/v1/documents/{document['id']}/send", headers=headers, json={"format": "docx"}
    )
    assert sent.status_code == 202, sent.text
    assert sent.json()["filename"] == "КП для Клиента.docx"

    entries = await redis.xrange("test:to_bot")
    assert len(entries) == 1, "ядро кладёт ровно одно событие доставки"
    _, fields = entries[0]
    assert fields["type"] == "document.ready"
    payload = DocumentReady.model_validate_json(fields["payload"])
    assert payload.max_user_id == 1 and payload.size > 0
    assert payload.filename == "КП для Клиента.docx"
    assert sent.json()["event_id"] == fields["id"]

    # Токен — единственный ключ к файлу: без Bearer, но ровно один раз.
    first = await client.get(f"/api/v1/documents/download/{payload.download_token}")
    assert first.status_code == 200 and first.content[:2] == b"PK"
    second = await client.get(f"/api/v1/documents/download/{payload.download_token}")
    assert second.status_code == 404 and second.json()["code"] == "document.token_invalid"


async def test_send_refuses_unfinished_document(
    client: AsyncClient, session: AsyncSession, redis, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    offer_id = next(t["id"] for t in templates if t["slug"] == "offer")
    document = (
        await client.post("/api/v1/documents", headers=headers, json={"template_id": offer_id})
    ).json()

    response = await client.post(
        f"/api/v1/documents/{document['id']}/send", headers=headers, json={"format": "docx"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "document.not_ready"
    assert await redis.xlen("test:to_bot") == 0, "неготовый документ не доходит до бота"


async def test_document_can_be_deleted_with_its_files(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    templates = (await client.get("/api/v1/templates", headers=headers)).json()
    offer_id = next(t["id"] for t in templates if t["slug"] == "offer")
    document = (
        await client.post("/api/v1/documents", headers=headers, json={"template_id": offer_id})
    ).json()

    deleted = await client.delete(f"/api/v1/documents/{document['id']}", headers=headers)
    assert deleted.status_code == 200 and deleted.json() == {"ok": True}
    assert (
        await client.get(f"/api/v1/documents/{document['id']}", headers=headers)
    ).status_code == 404
    assert (await client.get("/api/v1/documents", headers=headers)).json() == []
    # Повторное удаление — тоже 404: сценарий очистки должен быть безопасным.
    assert (
        await client.delete(f"/api/v1/documents/{document['id']}", headers=headers)
    ).status_code == 404


async def test_templates_can_be_filtered_by_slug(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    response = await client.get("/api/v1/templates?slug=invoice", headers=headers)
    assert [item["slug"] for item in response.json()] == ["invoice"]
    assert (await client.get("/api/v1/templates?slug=нет-такого", headers=headers)).json() == []


READY_OFFER_JSON = {
    "date": {"value": "24.09.2026"},
    "seller_name": {"value": "ООО «Ромашка»"},
    "client_name": {"value": "ООО «Клиент»"},
    "subject": {"value": "Разработка"},
    "scope": {"value": "Бэкенд и бот"},
    "total": {"value": "450 000"},
    "valid_until": {"value": "31.10.2026"},
}


async def test_history_summary_and_copy(
    client: AsyncClient, session: AsyncSession, redis, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    offer = (await client.get("/api/v1/templates?slug=offer", headers=headers)).json()[0]
    document = (
        await client.post("/api/v1/documents", headers=headers, json={"template_id": offer["id"]})
    ).json()
    await client.patch(
        f"/api/v1/documents/{document['id']}/fields",
        headers=headers,
        json={"values": READY_OFFER_JSON},
    )
    sent = await client.post(
        f"/api/v1/documents/{document['id']}/send", headers=headers, json={"format": "docx"}
    )
    assert sent.status_code == 202, sent.text

    history = await client.get(f"/api/v1/documents/{document['id']}/history", headers=headers)
    assert history.status_code == 200
    assert [fact["kind"] for fact in history.json()] == ["created", "ready", "rendered", "sent"]
    assert history.json()[-1]["format"] == "docx"

    (summary,) = (await client.get("/api/v1/documents", headers=headers)).json()
    assert summary["client"] == "ООО «Клиент»"
    assert summary["sent"]["format"] == "docx" and summary["sent"]["delivery"] == "pending"

    copy = await client.post(
        f"/api/v1/documents/{document['id']}/copy",
        headers=headers,
        json={"title": "КП на второй этап"},
    )
    assert copy.status_code == 201, copy.text
    body = copy.json()
    assert body["title"] == "КП на второй этап" and body["status"] == "draft"
    assert "date" not in body["values"] and "valid_until" not in body["values"]
    assert body["values"]["scope"]["value"] == "Бэкенд и бот"
    assert set(body["missing"]) == {"date", "valid_until"}
    no_body = await client.post(f"/api/v1/documents/{document['id']}/copy", headers=headers)
    assert no_body.status_code == 201 and no_body.json()["title"] == document["title"]


async def test_history_of_foreign_document_is_hidden(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    owner = await _auth(client, make_init_data, user_id=1)
    stranger = await _auth(client, make_init_data, user_id=2)
    offer = (await client.get("/api/v1/templates?slug=offer", headers=owner)).json()[0]
    document = (
        await client.post("/api/v1/documents", headers=owner, json={"template_id": offer["id"]})
    ).json()

    for method, path in (
        ("GET", f"/api/v1/documents/{document['id']}/history"),
        ("POST", f"/api/v1/documents/{document['id']}/copy"),
    ):
        response = await client.request(method, path, headers=stranger)
        assert response.status_code == 404, path
        assert response.json()["code"] == "document.not_found"


async def test_huge_ids_and_control_characters_are_422_not_500(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    too_big = 2**63
    for method, path, body in (
        ("GET", f"/api/v1/documents/{too_big}", None),
        ("GET", f"/api/v1/templates/{too_big}", None),
        ("DELETE", f"/api/v1/counterparties/{too_big}", None),
        ("POST", "/api/v1/documents", {"template_id": too_big}),
    ):
        response = await client.request(method, path, headers=headers, json=body)
        assert response.status_code == 422, (path, response.text)

    offer = (await client.get("/api/v1/templates?slug=offer", headers=headers)).json()[0]
    created = await client.post(
        "/api/v1/documents",
        headers=headers,
        json={"template_id": offer["id"], "title": "КП\x00 для​ Клиента"},
    )
    assert created.status_code == 201 and created.json()["title"] == "КП для Клиента"
    patched = await client.patch(
        f"/api/v1/documents/{created.json()['id']}/fields",
        headers=headers,
        json={"values": {"client_name": {"value": "ООО\x07 Клиент"}}},
    )
    assert patched.status_code == 200
    assert [e["code"] for e in patched.json()["errors"]] == ["field.control_chars"]
