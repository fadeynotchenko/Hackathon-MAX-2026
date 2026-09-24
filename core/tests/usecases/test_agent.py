"""Сценарии агента на подставной модели: что уходит модели и что попадает в документ."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldValue, ValueSource
from core.domain.exceptions import AppError
from core.usecases.agent import answer_question, draft_cover_letter, fill_from_message
from core.usecases.agent.prompts import fill_instructions
from core.usecases.documents import (
    confirm_fields,
    create_draft,
    ensure_builtin_templates,
    list_templates,
    set_fields,
)
from tests.fakes import FakeLLM
from tests.usecases.test_documents import make_user


async def _invoice(session: AsyncSession) -> tuple[int, int]:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    invoice = next(t for t in await list_templates(session, user_id=user_id, slug="invoice"))
    document = await create_draft(session, user_id=user_id, template_id=invoice.id)
    return user_id, document.id


async def test_agent_fills_only_valid_known_fields(session: AsyncSession) -> None:
    user_id, document_id = await _invoice(session)
    llm = FakeLLM(
        json_reply={
            "total": "120 000",
            "client_name": "ООО «Ромашка»",
            "seller_inn": "1234567890",
            "number": "",
            "invented_field": "что-то",
        }
    )

    result = await fill_from_message(
        session,
        user_id=user_id,
        document_id=document_id,
        message="Счёт на 120 тысяч для ООО «Ромашка», ИНН наш 1234567890",
        llm=llm,
    )

    assert set(result.filled) == {"total", "client_name"}
    assert [e.code for e in result.rejected] == ["field.inn_invalid"]
    total = result.document.values["total"]
    assert (total.value, total.source, total.confirmed) == ("120000.00", ValueSource.AGENT, False)
    assert "invented_field" not in result.document.values
    assert set(result.document.unconfirmed) == {"total", "client_name"}
    assert result.reply.startswith("Заполнил:")
    assert "Не принял" in result.reply and "Проверьте" in result.reply

    kind, messages, schema = llm.calls[0]
    assert kind == "json"
    assert schema is not None and schema["additionalProperties"] is False
    assert "seller_inn" in schema["properties"]
    assert "Ничего не придумывай" in messages[0].content
    assert messages[0].content.startswith(fill_instructions()), "с сегодняшней датой в правилах"
    assert messages[1].content.startswith("Счёт на 120 тысяч")


def test_fill_rules_carry_the_moscow_date() -> None:
    late_evening_utc = datetime(2026, 9, 24, 22, 30, tzinfo=UTC)
    rules = fill_instructions(late_evening_utc)
    assert "от сегодняшней (25.09.2026)" in rules, "в 01:30 по Москве уже 25-е"
    assert "{today}" not in rules


async def test_agent_values_need_confirmation_before_ready(session: AsyncSession) -> None:
    user_id, document_id = await _invoice(session)
    await set_fields(
        session,
        user_id=user_id,
        document_id=document_id,
        values={
            "number": FieldValue("7"),
            "date": FieldValue("24.09.2026"),
            "seller_name": FieldValue("ООО «Поставщик»"),
            "seller_inn": FieldValue("7707083893"),
            "seller_bank": FieldValue("ПАО Сбербанк"),
            "seller_bic": FieldValue("044525225"),
            "seller_account": FieldValue("40702810438000123459"),
            "item": FieldValue("Услуги"),
        },
    )
    llm = FakeLLM(json_reply={"total": "50 000", "client_name": "ООО «Клиент»"})
    result = await fill_from_message(
        session, user_id=user_id, document_id=document_id, message="50 тысяч, ООО Клиент", llm=llm
    )
    assert not result.document.ready and result.document.missing == ()

    confirmed = await confirm_fields(session, user_id=user_id, document_id=document_id)
    assert confirmed.ready and confirmed.status == "ready"
    assert confirmed.values["total"].source is ValueSource.AGENT


async def test_confirm_can_be_selective(session: AsyncSession) -> None:
    user_id, document_id = await _invoice(session)
    llm = FakeLLM(json_reply={"total": "50 000", "client_name": "ООО «Клиент»"})
    await fill_from_message(
        session, user_id=user_id, document_id=document_id, message="50 тысяч, Клиент", llm=llm
    )
    view = await confirm_fields(session, user_id=user_id, document_id=document_id, keys=["total"])
    assert view.unconfirmed == ("client_name",)


async def test_answer_uses_document_context(session: AsyncSession) -> None:
    user_id, document_id = await _invoice(session)
    llm = FakeLLM(text="  Не хватает номера и даты счёта.  ")
    answer = await answer_question(
        session, user_id=user_id, document_id=document_id, question="Чего не хватает?", llm=llm
    )
    assert answer == "Не хватает номера и даты счёта."
    system = llm.calls[0][1][0].content
    assert "Счёт на оплату" in system and "Не заполнено:" in system
    assert "не юридическая консультация" in system


async def test_cover_letter_is_drafted_from_the_document(session: AsyncSession) -> None:
    user_id, document_id = await _invoice(session)
    llm = FakeLLM(text="Добрый день! Направляем счёт на оплату.")
    text = await draft_cover_letter(session, user_id=user_id, document_id=document_id, llm=llm)
    assert text == "Добрый день! Направляем счёт на оплату."
    assert "Текст документа:" in llm.calls[0][1][1].content


async def test_disabled_agent_says_so(session: AsyncSession) -> None:
    user_id, document_id = await _invoice(session)
    with pytest.raises(AppError) as exc:
        await answer_question(
            session, user_id=user_id, document_id=document_id, question="?", llm=None
        )
    assert exc.value.code == "agent.unavailable" and exc.value.status_code == 503


async def test_provider_outage_is_reported_as_temporary(session: AsyncSession) -> None:
    user_id, document_id = await _invoice(session)
    with pytest.raises(AppError) as exc:
        await fill_from_message(
            session,
            user_id=user_id,
            document_id=document_id,
            message="счёт",
            llm=FakeLLM(unavailable=True),
        )
    assert exc.value.code == "agent.unavailable"
