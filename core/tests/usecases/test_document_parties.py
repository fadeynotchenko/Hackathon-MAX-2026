"""Стороны уже созданного черновика: «от кого» и «кому» выбираются в форме заполнения."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import FieldValue, ValueSource
from core.domain.exceptions import NotFoundError
from core.usecases.documents import (
    STATUS_DRAFT,
    STATUS_READY,
    create_counterparty,
    create_draft,
    create_organization,
    document_history,
    ensure_builtin_templates,
    get_document,
    list_documents,
    list_templates,
    set_fields,
    set_parties,
)
from tests.usecases.test_documents import make_user

ROMASHKA = {
    "inn": "7707083893",
    "kpp": "773601001",
    "bank": "ПАО Сбербанк",
    "bic": "044525225",
    "account": "40702810438000123459",
}
IP = {"inn": "500100732259"}
CLIENT = {"inn": "7707083893", "address": "г. Москва, ул. Вавилова, д. 19"}


async def _invoice(session: AsyncSession, user_id: int) -> int:
    await ensure_builtin_templates(session)
    return (await list_templates(session, user_id=user_id, slug="invoice"))[0].id


async def test_switching_organization_replaces_every_seller_field(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await create_organization(session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA)
    ip = await create_organization(session, user_id=user_id, name="ИП Нотченко", values=IP)
    draft = await create_draft(
        session, user_id=user_id, template_id=await _invoice(session, user_id)
    )
    await set_fields(
        session,
        user_id=user_id,
        document_id=draft.id,
        values={
            "seller_address": FieldValue("г. Москва, ул. Ленина, д. 1"),
            "number": FieldValue("17"),
            "date": FieldValue("01.09.2026"),
        },
    )

    switched = await set_parties(
        session, user_id=user_id, document_id=draft.id, organization_id=ip.id
    )

    assert switched.organization_id == ip.id
    assert switched.values["seller_name"].value == "ИП Нотченко"
    assert switched.values["seller_inn"].value == "500100732259"
    assert switched.values["seller_name"].source is ValueSource.PROFILE
    assert "seller_kpp" not in switched.values, "КПП «Ромашки» не едет к ИП"
    assert "seller_bank" not in switched.values
    assert "seller_address" not in switched.values, "набранное про прежнего продавца тоже уходит"
    assert switched.values["number"].value == "17", "остальные поля не трогаем"
    assert switched.values["date"].value == "2026-09-01", "дату по умолчанию заново не ставим"
    reloaded = await get_document(session, user_id=user_id, document_id=draft.id)
    assert reloaded.organization_id == ip.id and reloaded.values == switched.values


async def test_picking_counterparty_replaces_typed_client(session: AsyncSession) -> None:
    user_id = await make_user(session)
    card = await create_counterparty(session, user_id=user_id, name="ООО «Клиент»", values=IP)
    draft = await create_draft(
        session, user_id=user_id, template_id=await _invoice(session, user_id)
    )
    await set_fields(
        session,
        user_id=user_id,
        document_id=draft.id,
        values={
            "client_name": FieldValue("ООО «Набрано руками»"),
            "client_address": FieldValue("г. Тверь, ул. Советская, д. 5"),
        },
    )

    picked = await set_parties(
        session, user_id=user_id, document_id=draft.id, counterparty_id=card.id
    )

    assert picked.counterparty_id == card.id
    assert picked.values["client_name"].value == "ООО «Клиент»"
    assert picked.values["client_name"].source is ValueSource.COUNTERPARTY
    assert picked.values["client_inn"].value == "500100732259"
    assert "client_address" not in picked.values, "адрес прежнего клиента не остаётся"
    (summary,) = await list_documents(session, user_id=user_id)
    assert summary.counterparty_name == "ООО «Клиент»"


async def test_detaching_counterparty_keeps_what_the_person_typed(session: AsyncSession) -> None:
    user_id = await make_user(session)
    card = await create_counterparty(session, user_id=user_id, name="ООО «Клиент»", values=IP)
    draft = await create_draft(
        session,
        user_id=user_id,
        template_id=await _invoice(session, user_id),
        counterparty_id=card.id,
    )
    await set_fields(
        session,
        user_id=user_id,
        document_id=draft.id,
        values={"client_address": FieldValue("г. Тверь, ул. Советская, д. 5")},
    )

    detached = await set_parties(
        session, user_id=user_id, document_id=draft.id, counterparty_id=None
    )

    assert detached.counterparty_id is None
    assert "client_name" not in detached.values and "client_inn" not in detached.values
    assert detached.values["client_address"].value == "г. Тверь, ул. Советская, д. 5"
    (summary,) = await list_documents(session, user_id=user_id)
    assert summary.counterparty_name is None


async def test_detaching_organization_keeps_typed_seller_fields(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await create_organization(session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA)
    draft = await create_draft(
        session, user_id=user_id, template_id=await _invoice(session, user_id)
    )
    await set_fields(
        session,
        user_id=user_id,
        document_id=draft.id,
        values={"seller_director": FieldValue("Иванов Иван Иванович")},
    )

    detached = await set_parties(
        session, user_id=user_id, document_id=draft.id, organization_id=None
    )

    assert detached.organization_id is None
    assert not {"seller_name", "seller_inn", "seller_kpp"} & detached.values.keys()
    assert detached.values["seller_director"].value == "Иванов Иван Иванович"


async def test_both_parties_at_once_and_nothing_to_change(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await create_organization(session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA)
    ip = await create_organization(session, user_id=user_id, name="ИП Нотченко", values=IP)
    card = await create_counterparty(session, user_id=user_id, name="ООО «Клиент»", values=CLIENT)
    draft = await create_draft(
        session, user_id=user_id, template_id=await _invoice(session, user_id)
    )

    both = await set_parties(
        session,
        user_id=user_id,
        document_id=draft.id,
        organization_id=ip.id,
        counterparty_id=card.id,
    )
    assert (both.organization_id, both.counterparty_id) == (ip.id, card.id)
    assert both.values["seller_name"].value == "ИП Нотченко"
    assert both.values["client_address"].source is ValueSource.COUNTERPARTY

    untouched = await set_parties(session, user_id=user_id, document_id=draft.id)
    assert untouched.values == both.values and untouched.updated_at == both.updated_at


async def test_foreign_or_unknown_party_is_not_found_and_changes_nothing(
    session: AsyncSession,
) -> None:
    user_id = await make_user(session)
    stranger = await make_user(session, max_user_id=2)
    ours = await create_organization(
        session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA
    )
    theirs_org = await create_organization(session, user_id=stranger, name="Чужая", values=IP)
    theirs_card = await create_counterparty(session, user_id=stranger, name="Чужой", values=IP)
    draft = await create_draft(
        session, user_id=user_id, template_id=await _invoice(session, user_id)
    )

    with pytest.raises(NotFoundError) as org:
        await set_parties(
            session, user_id=user_id, document_id=draft.id, organization_id=theirs_org.id
        )
    assert org.value.code == "organization.not_found"
    with pytest.raises(NotFoundError) as card:
        await set_parties(
            session,
            user_id=user_id,
            document_id=draft.id,
            organization_id=None,
            counterparty_id=theirs_card.id,
        )
    assert card.value.code == "counterparty.not_found"
    with pytest.raises(NotFoundError) as unknown:
        await set_parties(session, user_id=user_id, document_id=draft.id, counterparty_id=10**9)
    assert unknown.value.code == "counterparty.not_found"
    with pytest.raises(NotFoundError) as document:
        await set_parties(session, user_id=stranger, document_id=draft.id, counterparty_id=None)
    assert document.value.code == "document.not_found"

    reloaded = await get_document(session, user_id=user_id, document_id=draft.id)
    assert reloaded.organization_id == ours.id, "организацию не отвязали из-за чужой карточки"
    assert reloaded.values == draft.values


async def test_status_follows_the_parties(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await create_organization(session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA)
    ip = await create_organization(session, user_id=user_id, name="ИП Нотченко", values=IP)
    card = await create_counterparty(session, user_id=user_id, name="ООО «Клиент»", values=IP)
    draft = await create_draft(
        session, user_id=user_id, template_id=await _invoice(session, user_id)
    )
    await set_fields(
        session,
        user_id=user_id,
        document_id=draft.id,
        values={
            "number": FieldValue("17"),
            "items": FieldValue('[{"name": "Разработка мини-приложения", "price": "450000"}]'),
        },
    )

    ready = await set_parties(
        session, user_id=user_id, document_id=draft.id, counterparty_id=card.id
    )
    assert ready.ready and ready.status == STATUS_READY, "карточка дала название клиента"

    detached = await set_parties(
        session, user_id=user_id, document_id=draft.id, counterparty_id=None
    )
    assert detached.status == STATUS_DRAFT and "client_name" in detached.missing

    again = await set_parties(
        session, user_id=user_id, document_id=draft.id, counterparty_id=card.id
    )
    assert again.status == STATUS_READY

    without_bank = await set_parties(
        session, user_id=user_id, document_id=draft.id, organization_id=ip.id
    )
    assert without_bank.status == STATUS_DRAFT
    assert {"seller_bank", "seller_bic", "seller_account"} <= set(without_bank.missing)

    facts = await document_history(session, user_id=user_id, document_id=draft.id)
    assert [fact.kind for fact in facts] == ["created", "ready", "ready"]
