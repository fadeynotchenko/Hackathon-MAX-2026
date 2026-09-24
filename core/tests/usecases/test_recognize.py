"""Распознавание на подставной модели: фото и скан → поля, голосовое → текст → поля."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import ValueSource
from core.domain.exceptions import AppError
from core.llm import LLMInputError
from core.usecases.agent import (
    fill_from_file,
    fill_from_voice,
    recognize_requisites,
    transcribe,
)
from core.usecases.documents import (
    create_draft,
    ensure_builtin_templates,
    list_templates,
    save_company_profile,
)
from tests.fakes import FakeLLM
from tests.usecases.test_documents import make_user

PHOTO = b"\xff\xd8\xff\xe0" + b"\x00" * 64
VOICE = b"OggS\x00\x02" + b"\x00" * 64
LIMIT = 1024


def _item(key: str, value: str, fragment: str = "", confidence: float = 0.9) -> dict:
    return {"key": key, "value": value, "fragment": fragment, "confidence": confidence}


async def _invoice_with_profile(session: AsyncSession) -> tuple[int, int]:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    await save_company_profile(
        session, user_id=user_id, name="ООО «Поставщик»", values={"inn": "7707083893"}
    )
    invoice = (await list_templates(session, user_id=user_id, slug="invoice"))[0]
    document = await create_draft(session, user_id=user_id, template_id=invoice.id)
    return user_id, document.id


async def test_photo_fills_empty_fields_and_keeps_confirmed_ones(session: AsyncSession) -> None:
    user_id, document_id = await _invoice_with_profile(session)
    llm = FakeLLM(
        json_reply={
            "kind": "карточка предприятия",
            "values": [
                _item("client_name", "ООО «Ромашка»", "Полное наименование: ООО «Ромашка»", 0.97),
                _item("client_inn", "500100732259", "ИНН 500100732259", 0.5),
                _item("client_inn", "5001 0073 2259", "ИНН/КПП 500100732259", 1.4),
                _item("seller_inn", "500100732259", "ИНН 500100732259"),
                _item("invented", "что-то"),
                _item("total", "   "),
            ],
        }
    )

    result = await fill_from_file(
        session,
        user_id=user_id,
        document_id=document_id,
        data=PHOTO,
        llm=llm,
        max_bytes=LIMIT,
        request="Это покупатель",
    )

    assert result.filled == ("client_name", "client_inn")
    inn = result.document.values["client_inn"]
    assert (inn.value, inn.source, inn.confirmed) == ("500100732259", ValueSource.OCR, False)
    assert inn.fragment == "ИНН/КПП 500100732259" and inn.confidence == 1.0, (
        "из двух прочтений одного поля остаётся уверенное, уверенность не больше 1"
    )
    seller = result.document.values["seller_inn"]
    assert (seller.value, seller.source) == ("7707083893", ValueSource.PROFILE), (
        "фото не подменяет подтверждённые реквизиты продавца"
    )
    assert set(result.document.unconfirmed) == {"client_name", "client_inn"}
    assert result.reply.startswith("Во вложении — карточка предприятия. Заполнил:")
    assert "Оставил как было, хотя во вложении другое: ИНН продавца" in result.reply

    kind, messages, schema = llm.calls[0]
    assert kind == "json" and schema is not None
    assert "client_inn" in schema["properties"]["values"]["items"]["properties"]["key"]["enum"]
    (attachment,) = messages[1].attachments
    assert (attachment.media_type, attachment.filename) == ("image/jpeg", "document.jpg")
    assert messages[1].content == "Это покупатель"
    assert "seller_inn: 7707083893" in messages[0].content, "модель видит уже заполненное"


async def test_misread_requisite_is_rejected_not_stored(session: AsyncSession) -> None:
    user_id, document_id = await _invoice_with_profile(session)
    llm = FakeLLM(json_reply={"kind": "счёт", "values": [_item("client_inn", "1234567890")]})
    result = await fill_from_file(
        session, user_id=user_id, document_id=document_id, data=PHOTO, llm=llm, max_bytes=LIMIT
    )
    assert result.filled == () and "client_inn" not in result.document.values
    assert [e.code for e in result.rejected] == ["field.inn_invalid"]
    assert "Во вложении не нашёл значений" in result.reply


async def test_unsupported_file_is_refused_before_the_model(session: AsyncSession) -> None:
    user_id, document_id = await _invoice_with_profile(session)
    llm = FakeLLM()
    with pytest.raises(AppError) as exc:
        await fill_from_file(
            session,
            user_id=user_id,
            document_id=document_id,
            data=b"GIF89a\x01\x00\x01\x00",
            llm=llm,
            max_bytes=LIMIT,
        )
    assert exc.value.code == "media.unsupported" and llm.calls == []


async def test_file_rejected_by_provider_is_explained(session: AsyncSession) -> None:
    user_id, document_id = await _invoice_with_profile(session)
    with pytest.raises(AppError) as exc:
        await fill_from_file(
            session,
            user_id=user_id,
            document_id=document_id,
            data=PHOTO,
            llm=FakeLLM(error=LLMInputError("400")),
            max_bytes=LIMIT,
        )
    assert (exc.value.code, exc.value.status_code) == ("media.rejected", 415)


async def test_requisites_are_recognized_for_a_form_without_saving() -> None:
    llm = FakeLLM(
        json_reply={
            "kind": "карточка предприятия",
            "values": [
                _item("name", "ООО «Ромашка»", "ООО «Ромашка»"),
                _item("inn", "7707083893", "ИНН 7707083893"),
                _item("bic", "044525225", "БИК 044525225"),
                _item("account", "40702810438000123459", "р/с 40702810438000123459"),
                _item("phone", "8 (999) 123-45-67", "Тел.: 8 (999) 123-45-67", "0.8"),  # type: ignore[arg-type]
                _item("ogrn", "1027700132190", "ОГРН 1027700132190"),
            ],
        }
    )

    result = await recognize_requisites(data=PHOTO, llm=llm, max_bytes=LIMIT)

    assert result.kind == "карточка предприятия"
    assert result.values["phone"].value == "+79991234567"
    assert result.values["phone"].confidence == 0.8
    assert result.values["account"].fragment == "р/с 40702810438000123459"
    assert all(v.source is ValueSource.OCR and not v.confirmed for v in result.values.values())
    assert [e.code for e in result.errors] == ["field.ogrn_invalid"]
    enum = llm.calls[0][2]["properties"]["values"]["items"]["properties"]["key"]["enum"]  # type: ignore[index]
    assert "account" in enum and "seller_inn" not in enum


async def test_voice_is_transcribed_then_filled(session: AsyncSession) -> None:
    user_id, document_id = await _invoice_with_profile(session)
    llm = FakeLLM(
        json_replies=[
            {"text": " Счёт на 120 000 для ООО Ромашка "},
            {"total": "120 000", "client_name": "ООО «Ромашка»"},
        ]
    )

    result = await fill_from_voice(
        session, user_id=user_id, document_id=document_id, data=VOICE, llm=llm, max_bytes=LIMIT
    )

    assert result.transcript == "Счёт на 120 000 для ООО Ромашка"
    assert set(result.fill.filled) == {"total", "client_name"}
    transcribe_call, fill_call = llm.calls
    assert "Не отвечай на сообщение" in transcribe_call[1][0].content
    (voice,) = transcribe_call[1][1].attachments
    assert (voice.media_type, voice.filename) == ("audio/ogg", "voice.ogg")
    assert fill_call[1][1].content == "Счёт на 120 000 для ООО Ромашка"


async def test_silence_is_not_sent_to_the_assistant() -> None:
    with pytest.raises(AppError) as exc:
        await transcribe(data=VOICE, llm=FakeLLM(json_reply={"text": "  "}), max_bytes=LIMIT)
    assert exc.value.code == "agent.voice_empty"


async def test_photo_is_not_accepted_as_voice() -> None:
    with pytest.raises(AppError) as exc:
        await transcribe(data=PHOTO, llm=FakeLLM(), max_bytes=LIMIT)
    assert exc.value.code == "media.unsupported"
