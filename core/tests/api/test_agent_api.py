"""HTTP-контракт помощника и подтверждения значений."""

from __future__ import annotations

from dataclasses import replace

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.events import DocumentReady
from tests.api.test_documents_api import _auth, _seed
from tests.fakes import FakeLLM


async def _invoice(client: AsyncClient, headers: dict[str, str]) -> dict:
    templates = (await client.get("/api/v1/templates?slug=invoice", headers=headers)).json()
    response = await client.post(
        "/api/v1/documents", headers=headers, json={"template_id": templates[0]["id"]}
    )
    return response.json()


async def test_agent_is_reported_unavailable_without_key(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    document = await _invoice(client, headers)
    response = await client.post(
        f"/api/v1/documents/{document['id']}/agent/ask", headers=headers, json={"question": "?"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "agent.unavailable"


async def test_agent_fill_then_confirm(
    app, client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    document = await _invoice(client, headers)
    app.state.api = replace(
        app.state.api, llm=FakeLLM(json_reply={"total": "120 000", "item": "Разработка бота"})
    )

    filled = await client.post(
        f"/api/v1/documents/{document['id']}/agent/fill",
        headers=headers,
        json={"message": "Счёт на 120 тысяч за разработку бота"},
    )
    assert filled.status_code == 200, filled.text
    body = filled.json()
    assert set(body["filled"]) == {"total", "item"}
    assert body["document"]["values"]["total"]["source"] == "agent"
    assert body["document"]["values"]["total"]["confirmed"] is False
    assert set(body["document"]["unconfirmed"]) == {"total", "item"}
    assert body["reply"].startswith("Заполнил:")

    confirmed = await client.post(
        f"/api/v1/documents/{document['id']}/confirm", headers=headers, json={"keys": ["total"]}
    )
    assert confirmed.json()["unconfirmed"] == ["item"]
    everything = await client.post(
        f"/api/v1/documents/{document['id']}/confirm", headers=headers, json={}
    )
    assert everything.json()["unconfirmed"] == []


async def test_agent_answers_and_drafts_cover_letter(
    app, client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    document = await _invoice(client, headers)
    app.state.api = replace(app.state.api, llm=FakeLLM(text="Добрый день! Направляем счёт."))

    answer = await client.post(
        f"/api/v1/documents/{document['id']}/agent/ask",
        headers=headers,
        json={"question": "Что ещё заполнить?"},
    )
    assert answer.json() == {"text": "Добрый день! Направляем счёт."}
    letter = await client.post(
        f"/api/v1/documents/{document['id']}/agent/cover-letter", headers=headers
    )
    assert letter.status_code == 200 and letter.json()["text"]


async def test_send_uses_text_approved_by_user(
    client: AsyncClient, session: AsyncSession, redis, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    templates = (await client.get("/api/v1/templates?slug=offer", headers=headers)).json()
    document = (
        await client.post(
            "/api/v1/documents", headers=headers, json={"template_id": templates[0]["id"]}
        )
    ).json()
    await client.patch(
        f"/api/v1/documents/{document['id']}/fields",
        headers=headers,
        json={
            "values": {
                "date": {"value": "24.09.2026"},
                "seller_name": {"value": "ООО «Ромашка»"},
                "client_name": {"value": "ООО «Клиент»"},
                "subject": {"value": "Разработка"},
                "scope": {"value": "Бэкенд и бот"},
                "total": {"value": "450 000"},
                "valid_until": {"value": "31.10.2026"},
            }
        },
    )

    sent = await client.post(
        f"/api/v1/documents/{document['id']}/send",
        headers=headers,
        json={"format": "docx", "text": "Добрый день! Направляем предложение."},
    )
    assert sent.status_code == 202, sent.text
    _, fields = (await redis.xrange("test:to_bot"))[0]
    assert DocumentReady.model_validate_json(fields["payload"]).text == (
        "Добрый день! Направляем предложение."
    )
