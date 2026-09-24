"""Свои организации: основная, выбор при создании документа, копия от той же организации."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.exceptions import NotFoundError, ValidationError
from core.usecases.agent.chat import named_organization
from core.usecases.documents import (
    copy_document,
    create_draft,
    create_organization,
    delete_organization,
    ensure_builtin_templates,
    list_organizations,
    list_templates,
    update_organization,
)
from tests.usecases.test_documents import make_user

ROMASHKA = {"inn": "7707083893"}
IP = {"inn": "500100732259"}


async def _invoice(session: AsyncSession, user_id: int) -> int:
    await ensure_builtin_templates(session)
    return (await list_templates(session, user_id=user_id, slug="invoice"))[0].id


async def test_first_is_default_and_default_can_move(session: AsyncSession) -> None:
    user_id = await make_user(session)
    first = await create_organization(
        session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA
    )
    second = await create_organization(session, user_id=user_id, name="ИП Нотченко", values=IP)
    assert first.is_default and not second.is_default, "первая заведённая — основная сама"

    await update_organization(
        session,
        user_id=user_id,
        organization_id=second.id,
        name="ИП Нотченко",
        values=IP,
        is_default=True,
    )
    listed = await list_organizations(session, user_id=user_id)
    assert [(o.name, o.is_default) for o in listed] == [
        ("ИП Нотченко", True),
        ("ООО «Ромашка»", False),
    ], "основная одна и стоит первой"


async def test_deleting_default_promotes_the_next(session: AsyncSession) -> None:
    user_id = await make_user(session)
    first = await create_organization(
        session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA
    )
    await create_organization(session, user_id=user_id, name="ИП Нотченко", values=IP)
    await delete_organization(session, user_id=user_id, organization_id=first.id)
    (left,) = await list_organizations(session, user_id=user_id)
    assert left.name == "ИП Нотченко" and left.is_default


async def test_duplicate_inn_and_foreign_organization_are_refused(session: AsyncSession) -> None:
    user_id = await make_user(session)
    stranger = await make_user(session, max_user_id=2)
    await create_organization(session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA)
    with pytest.raises(ValidationError):
        await create_organization(session, user_id=user_id, name="Двойник", values=ROMASHKA)
    theirs = await create_organization(session, user_id=stranger, name="Чужая", values=IP)
    with pytest.raises(NotFoundError):
        await create_draft(
            session,
            user_id=user_id,
            template_id=await _invoice(session, user_id),
            organization_id=theirs.id,
        )


async def test_document_is_from_the_chosen_organization_and_copy_keeps_it(
    session: AsyncSession,
) -> None:
    user_id = await make_user(session)
    await create_organization(session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA)
    ip = await create_organization(session, user_id=user_id, name="ИП Нотченко", values=IP)
    invoice = await _invoice(session, user_id)

    default = await create_draft(session, user_id=user_id, template_id=invoice)
    chosen = await create_draft(
        session, user_id=user_id, template_id=invoice, organization_id=ip.id
    )

    assert default.values["seller_name"].value == "ООО «Ромашка»", "без выбора — основная"
    assert chosen.organization_id == ip.id
    assert chosen.values["seller_inn"].value == "500100732259"
    copy = await copy_document(session, user_id=user_id, document_id=chosen.id)
    assert copy.organization_id == ip.id and copy.values["seller_name"].value == "ИП Нотченко"


async def test_copy_of_a_document_from_deleted_organization_goes_from_default(
    session: AsyncSession,
) -> None:
    user_id = await make_user(session)
    await create_organization(session, user_id=user_id, name="ООО «Ромашка»", values=ROMASHKA)
    ip = await create_organization(session, user_id=user_id, name="ИП Нотченко", values=IP)
    source = await create_draft(
        session,
        user_id=user_id,
        template_id=await _invoice(session, user_id),
        organization_id=ip.id,
    )
    await delete_organization(session, user_id=user_id, organization_id=ip.id)
    copy = await copy_document(session, user_id=user_id, document_id=source.id)
    assert copy.values["seller_name"].value == "ООО «Ромашка»"


async def test_chat_picks_the_organization_named_in_the_message(session: AsyncSession) -> None:
    user_id = await make_user(session)
    romashka = await create_organization(
        session,
        user_id=user_id,
        name="Общество с ограниченной ответственностью «Ромашка»",
        values=ROMASHKA,
    )
    ip = await create_organization(session, user_id=user_id, name="ИП Нотченко Фадей", values=IP)
    orgs = await list_organizations(session, user_id=user_id)

    assert named_organization(orgs, "счёт от ип нотченко для ооо лютик") == ip.id
    assert named_organization(orgs, "договор между ООО Рога и копыта и ромашкой") == romashka.id
    assert named_organization(orgs, "общество с ограниченной ответственностью Лютик") is None, (
        "слова правовой формы — не имя организации"
    )
    assert named_organization(orgs, "от Ромашки и Нотченко") is None, "двоих не угадываем"
