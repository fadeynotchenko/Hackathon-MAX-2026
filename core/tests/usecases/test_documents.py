"""Сценарии документов: каталог шаблонов, подстановка реквизитов, заполнение."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import UserRepository, UserUpsert
from core.domain.documents import BLANK, FieldValue, ValueSource
from core.domain.exceptions import NotFoundError, ValidationError
from core.usecases.documents import (
    STATUS_DRAFT,
    STATUS_READY,
    create_counterparty,
    create_draft,
    create_organization,
    ensure_builtin_templates,
    get_document,
    get_template,
    list_documents,
    list_templates,
    set_fields,
)
from core.usecases.documents.builtin import BUILTIN_TEMPLATES

MARKER = re.compile(r"{{\s*(\w+)\s*}}")


async def make_user(session: AsyncSession, max_user_id: int = 1) -> int:
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(max_user_id=max_user_id, first_name="Владелец"),
        touch_login=False,
        now=datetime.now(UTC),
    )
    return user.id


def test_builtin_bodies_only_use_declared_fields() -> None:
    for template in BUILTIN_TEMPLATES:
        keys = {spec.key for spec in template.fields}
        used = set(MARKER.findall(template.body))
        assert used <= keys, f"{template.slug}: в теле есть поля без описания: {used - keys}"


async def test_builtin_templates_are_seeded_idempotently(session: AsyncSession) -> None:
    user_id = await make_user(session)
    assert await ensure_builtin_templates(session) == len(BUILTIN_TEMPLATES)
    await ensure_builtin_templates(session)
    templates = await list_templates(session, user_id=user_id)
    assert len(templates) == len(BUILTIN_TEMPLATES)
    invoice = next(t for t in templates if t.slug == "invoice")
    assert invoice.is_builtin and invoice.body_format == "text"
    assert {spec.key for spec in invoice.fields} >= {"seller_inn", "client_name", "total"}


async def test_draft_is_prefilled_from_profile_and_counterparty(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    await create_organization(
        session,
        user_id=user_id,
        name="ООО «Ромашка»",
        values={
            "inn": "7707083893",
            "bic": "044525225",
            "account": "40702810438000123459",
            "bank": "ПАО Сбербанк",
        },
    )
    client = await create_counterparty(
        session, user_id=user_id, name="ООО «Клиент»", values={"inn": "500100732259"}
    )
    invoice = next(t for t in await list_templates(session, user_id=user_id) if t.slug == "invoice")

    document = await create_draft(
        session, user_id=user_id, template_id=invoice.id, counterparty_id=client.id
    )

    assert document.values["seller_name"].source is ValueSource.PROFILE
    assert document.values["seller_inn"].value == "7707083893"
    assert document.values["client_name"].source is ValueSource.COUNTERPARTY
    assert document.status == STATUS_DRAFT
    assert set(document.missing) == {"number", "date", "item", "total"}
    assert BLANK in document.preview, "незаполненное поле видно прочерком"
    assert "ПАО Сбербанк" in document.preview


async def test_filling_fields_makes_document_ready(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    offer = next(t for t in await list_templates(session, user_id=user_id) if t.slug == "offer")
    document = await create_draft(session, user_id=user_id, template_id=offer.id)

    filled = await set_fields(
        session,
        user_id=user_id,
        document_id=document.id,
        values={
            "date": FieldValue("23.09.2026"),
            "seller_name": FieldValue("ООО «Ромашка»"),
            "client_name": FieldValue("ООО «Клиент»"),
            "subject": FieldValue("Разработка мини-приложения"),
            "scope": FieldValue("Бэкенд, бот, мини-апп"),
            "total": FieldValue("450 000"),
            "valid_until": FieldValue("31.10.2026"),
        },
        title="КП для «Клиента»",
    )

    assert filled.ready and filled.status == STATUS_READY
    assert filled.title == "КП для «Клиента»"
    assert "450 000,00" in filled.preview
    assert "23.09.2026" in filled.preview
    assert BLANK in filled.preview, "необязательные поля остаются прочерками"


async def test_bad_value_is_reported_and_not_saved(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    offer = next(t for t in await list_templates(session, user_id=user_id) if t.slug == "offer")
    document = await create_draft(session, user_id=user_id, template_id=offer.id)

    result = await set_fields(
        session,
        user_id=user_id,
        document_id=document.id,
        values={"total": FieldValue("сколько-то"), "client_name": FieldValue("ООО «Клиент»")},
    )

    assert [e.code for e in result.errors] == ["field.money_invalid"]
    assert "total" not in result.values
    assert result.values["client_name"].value == "ООО «Клиент»"


async def test_empty_value_clears_field(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    offer = next(t for t in await list_templates(session, user_id=user_id) if t.slug == "offer")
    document = await create_draft(session, user_id=user_id, template_id=offer.id)
    with_value = await set_fields(
        session,
        user_id=user_id,
        document_id=document.id,
        values={"client_name": FieldValue("ООО «Клиент»", ValueSource.OCR, confirmed=False)},
    )
    assert with_value.unconfirmed == ("client_name",)

    cleared = await set_fields(
        session, user_id=user_id, document_id=document.id, values={"client_name": FieldValue("")}
    )
    assert "client_name" not in cleared.values
    assert "client_name" in cleared.missing


async def test_documents_and_templates_are_private(session: AsyncSession) -> None:
    owner_id = await make_user(session, max_user_id=1)
    stranger_id = await make_user(session, max_user_id=2)
    await ensure_builtin_templates(session)
    offer = next(t for t in await list_templates(session, user_id=owner_id) if t.slug == "offer")
    document = await create_draft(session, user_id=owner_id, template_id=offer.id)

    with pytest.raises(NotFoundError):
        await get_document(session, user_id=stranger_id, document_id=document.id)
    assert await list_documents(session, user_id=stranger_id) == []
    assert len(await list_documents(session, user_id=owner_id)) == 1
    # Встроенный шаблон общий: приватны документы и чужие шаблоны, а не каталог.
    assert await get_template(session, user_id=stranger_id, template_id=offer.id)


async def test_counterparty_requisites_are_validated(session: AsyncSession) -> None:
    user_id = await make_user(session)
    with pytest.raises(ValidationError):
        await create_counterparty(
            session, user_id=user_id, name="ООО «Опечатка»", values={"inn": "1234567890"}
        )
    created = await create_counterparty(
        session, user_id=user_id, name="ООО «Клиент»", values={"inn": "500100732259"}
    )
    assert created.inn == "500100732259"
    with pytest.raises(ValidationError):
        await create_counterparty(
            session, user_id=user_id, name="Ещё раз", values={"inn": "500100732259"}
        )
