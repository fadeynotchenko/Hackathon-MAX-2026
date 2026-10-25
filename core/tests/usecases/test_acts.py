"""Акт по счёту или договору: стороны, позиции и основание переходят сами."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldValue, ValueSource
from core.domain.exceptions import AppError
from core.usecases.documents import (
    create_act,
    create_draft,
    ensure_builtin_templates,
    list_templates,
    set_fields,
)
from tests.usecases.test_documents import make_user

SITE = json.dumps([{"name": "Сайт", "quantity": "1", "unit": "усл.", "price": "120000.00"}])


async def _document(session: AsyncSession, user_id: int, slug: str, values: dict) -> int:
    await ensure_builtin_templates(session)
    (template,) = await list_templates(session, user_id=user_id, slug=slug)
    draft = await create_draft(session, user_id=user_id, template_id=template.id)
    await set_fields(
        session,
        user_id=user_id,
        document_id=draft.id,
        values={key: FieldValue(value) for key, value in values.items()},
    )
    return draft.id


async def test_act_by_invoice_takes_its_items_and_parties(session: AsyncSession) -> None:
    user_id = await make_user(session)
    invoice = await _document(
        session,
        user_id,
        "invoice",
        {
            "number": "17",
            "date": "01.10.2026",
            "client_name": "ООО «Альфа»",
            "client_inn": "5003102144",
            "seller_name": "ООО «Ромашка»",
            "seller_inn": "7728417603",
            "items": SITE,
        },
    )

    act = await create_act(session, user_id=user_id, document_id=invoice)

    assert act.template.kind == "act" and act.id != invoice
    assert act.values["client_name"].value == "ООО «Альфа»"
    assert act.values["seller_inn"].value == "7728417603"
    assert json.loads(act.values["items"].value)[0]["name"] == "Сайт"
    assert act.values["basis"].value == "Счёт на оплату № 17 от 01.10.2026"
    assert act.values["basis"].source is ValueSource.DEFAULT
    assert not act.unconfirmed, "подтверждённое в счёте не просит подтверждения снова"
    assert "number" not in act.values or act.values["number"].value != "17"


async def test_act_by_contract_gets_one_line_from_subject_and_total(
    session: AsyncSession,
) -> None:
    user_id = await make_user(session)
    contract = await _document(
        session,
        user_id,
        "service-contract",
        {"client_name": "ООО «Вега»", "subject": "Уборка офиса", "total": "30000"},
    )

    act = await create_act(session, user_id=user_id, document_id=contract)

    (line,) = json.loads(act.values["items"].value)
    assert (line["name"], line["price"], line["quantity"]) == ("Уборка офиса", "30000.00", "1")
    assert act.values["basis"].value.startswith("Договор оказания услуг")


async def test_act_preview_comes_from_its_blank(session: AsyncSession) -> None:
    user_id = await make_user(session)
    invoice = await _document(
        session, user_id, "invoice", {"client_name": "ООО «Альфа»", "items": SITE}
    )
    act = await create_act(session, user_id=user_id, document_id=invoice)
    assert "Акт №" in act.preview and "ООО «Альфа»" in act.preview
    assert "претензий по объёму" in act.preview


async def test_act_of_an_act_is_refused(session: AsyncSession) -> None:
    user_id = await make_user(session)
    act_id = await _document(session, user_id, "act", {"client_name": "ООО «Альфа»"})
    with pytest.raises(AppError) as error:
        await create_act(session, user_id=user_id, document_id=act_id)
    assert error.value.code == "act.unsupported"
