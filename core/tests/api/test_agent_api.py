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


PHOTO = b"\xff\xd8\xff\xe0" + b"\x00" * 64
VOICE = b"OggS\x00\x02" + b"\x00" * 64


async def test_photo_is_recognized_into_document(
    app, client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    document = await _invoice(client, headers)
    llm = FakeLLM(
        json_reply={
            "kind": "карточка предприятия",
            "values": [
                {
                    "key": "client_inn",
                    "value": "7707083893",
                    "fragment": "ИНН 7707083893",
                    "confidence": 0.95,
                }
            ],
        }
    )
    app.state.api = replace(app.state.api, llm=llm)

    response = await client.post(
        f"/api/v1/documents/{document['id']}/agent/recognize?hint=это покупатель",
        headers=headers | {"Content-Type": "image/jpeg"},
        content=PHOTO,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filled"] == ["client_inn"]
    value = body["document"]["values"]["client_inn"]
    assert value["source"] == "ocr" and value["confirmed"] is False
    assert value["fragment"] == "ИНН 7707083893" and value["confidence"] == 0.95
    assert body["reply"].startswith("Во вложении — карточка предприятия.")
    assert llm.calls[0][1][1].content == "это покупатель"


async def test_upload_limits_and_formats_are_enforced(
    app, client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    document = await _invoice(client, headers)
    llm = FakeLLM()
    app.state.api = replace(
        app.state.api,
        llm=llm,
        files_config=replace(app.state.api.files_config, media_max_bytes=100),
    )
    url = f"/api/v1/documents/{document['id']}/agent/recognize"

    too_large = await client.post(url, headers=headers, content=PHOTO + b"\x00" * 200)
    gif = await client.post(url, headers=headers, content=b"GIF89a\x01\x00\x01\x00")
    empty = await client.post(url, headers=headers, content=b"")

    assert (too_large.status_code, too_large.json()["code"]) == (413, "media.too_large")
    assert (gif.status_code, gif.json()["code"]) == (415, "media.unsupported")
    assert (empty.status_code, empty.json()["code"]) == (422, "media.empty")
    assert llm.calls == [], "до модели доходит только годный файл"


async def test_recognition_needs_auth_and_agent(
    client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    anonymous = await client.post("/api/v1/requisites/recognize", content=PHOTO)
    assert anonymous.status_code == 401
    headers = await _auth(client, make_init_data)
    disabled = await client.post("/api/v1/requisites/recognize", headers=headers, content=PHOTO)
    assert (disabled.status_code, disabled.json()["code"]) == (503, "agent.unavailable")


async def test_requisites_are_recognized_for_the_card_form(
    app, client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    headers = await _auth(client, make_init_data)
    app.state.api = replace(
        app.state.api,
        llm=FakeLLM(
            json_reply={
                "kind": "карточка предприятия",
                "values": [
                    {"key": "name", "value": "ООО «Ромашка»", "fragment": "", "confidence": 1},
                    {"key": "kpp", "value": "12345", "fragment": "КПП 12345", "confidence": 0.4},
                ],
            }
        ),
    )

    response = await client.post(
        "/api/v1/requisites/recognize",
        headers=headers | {"Content-Type": "image/jpeg"},
        content=PHOTO,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "карточка предприятия"
    assert body["values"]["name"]["value"] == "ООО «Ромашка»"
    assert body["values"]["name"]["fragment"] is None
    assert [e["code"] for e in body["errors"]] == ["field.kpp_invalid"]
    counterparties = (await client.get("/api/v1/counterparties", headers=headers)).json()
    assert counterparties == [], "распознавание карточку не заводит"


async def test_voice_fills_document(
    app, client: AsyncClient, session: AsyncSession, make_init_data
) -> None:
    await _seed(session)
    headers = await _auth(client, make_init_data)
    document = await _invoice(client, headers)
    app.state.api = replace(
        app.state.api,
        llm=FakeLLM(json_replies=[{"text": "Сумма 50 000"}, {"total": "50 000"}]),
    )

    response = await client.post(
        f"/api/v1/documents/{document['id']}/agent/voice",
        headers=headers | {"Content-Type": "audio/ogg"},
        content=VOICE,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"] == "Сумма 50 000"
    assert body["filled"] == ["total"]
    assert body["document"]["values"]["total"]["value"] == "50000.00"
