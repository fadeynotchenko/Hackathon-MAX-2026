"""Сценарии документов: каталог шаблонов, подстановка реквизитов, заполнение."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Template, TemplateFile
from core.db.repositories import UserRepository, UserUpsert
from core.domain.documents import (
    BLANK,
    FieldType,
    FieldValue,
    ValueSource,
    fill_context,
    template_markers,
    validate_fields,
)
from core.domain.exceptions import NotFoundError, ValidationError
from core.files import docx_layout, docx_lines, fill_docx
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
from core.usecases.documents.demo import DEMO_CLIENT, DEMO_SELLER


async def make_user(session: AsyncSession, max_user_id: int = 1) -> int:
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(max_user_id=max_user_id, first_name="Владелец"),
        touch_login=False,
        now=datetime.now(UTC),
    )
    return user.id


def test_builtin_blanks_match_declared_fields() -> None:
    """Каждый маркер бланка описан полем, и каждое поле где-то стоит в бланке."""
    for template in BUILTIN_TEMPLATES:
        keys = {spec.key for spec in template.fields}
        used = set(template_markers("\n".join(docx_layout(template.blank_bytes()))))
        assert used == keys, f"{template.slug}: без описания {used - keys}, без места {keys - used}"


async def test_builtin_templates_are_seeded_idempotently(session: AsyncSession) -> None:
    user_id = await make_user(session)
    assert await ensure_builtin_templates(session) == len(BUILTIN_TEMPLATES)
    await ensure_builtin_templates(session)
    templates = await list_templates(session, user_id=user_id)
    assert len(templates) == len(BUILTIN_TEMPLATES)
    invoice = next(t for t in templates if t.slug == "invoice")
    assert invoice.is_builtin and invoice.body_format == "docx"
    assert invoice.file is not None and invoice.file.filename == "invoice.docx"
    assert {spec.key for spec in invoice.fields} >= {"seller_inn", "client_name", "total"}
    files = (await session.execute(select(TemplateFile))).scalars().all()
    assert len(files) == len(BUILTIN_TEMPLATES), "бланк не записывается второй раз"
    assert all(file.owner_user_id is None for file in files)


async def test_changed_builtin_keeps_old_edition_for_its_documents(
    session: AsyncSession,
) -> None:
    """Счёт, созданный на прошлой редакции стандартного шаблона, не меняет вида
    после обновления бланка: он переезжает на архивную копию."""
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    (invoice,) = await list_templates(session, user_id=user_id, slug="invoice")
    document = await create_draft(session, user_id=user_id, template_id=invoice.id)
    row = await session.get(Template, invoice.id)
    assert row is not None
    row.body = "Счёт прошлой редакции {{number}}"
    await session.flush()

    await ensure_builtin_templates(session)

    kept = await get_document(session, user_id=user_id, document_id=document.id)
    assert kept.template.id != invoice.id and kept.template.body.startswith("Счёт прошлой")
    (live,) = await list_templates(session, user_id=user_id, slug="invoice")
    assert live.id == invoice.id and "Счет на оплату №" in live.body
    await ensure_builtin_templates(session)
    archived = await session.execute(select(Template).where(Template.origin_id == invoice.id))
    assert len(archived.scalars().all()) == 1, "неизменный бланк новую редакцию не плодит"


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
    assert set(document.missing) == {"number", "item", "total"}, "дату счёта ставит система"
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
    assert "от «23» сентября 2026 г." in filled.preview, "дата письма — одной строкой"
    assert "Четыреста пятьдесят тысяч рублей 00 копеек" in filled.preview, "сумма прописью"
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


async def test_rejected_edit_keeps_the_previous_value(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    (offer,) = await list_templates(session, user_id=user_id, slug="offer")
    document = await create_draft(session, user_id=user_id, template_id=offer.id)
    await set_fields(
        session, user_id=user_id, document_id=document.id, values={"total": FieldValue("120000")}
    )

    edited = await set_fields(
        session,
        user_id=user_id,
        document_id=document.id,
        values={"total": FieldValue("сто пятьдесят")},
    )

    assert [e.code for e in edited.errors] == ["field.money_invalid"]
    assert edited.values["total"].value == "120000.00", "опечатка не стирает прошлую сумму"
    reloaded = await get_document(session, user_id=user_id, document_id=document.id)
    assert reloaded.values["total"].value == "120000.00" and reloaded.errors == ()


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


async def test_archive_tells_same_invoices_apart_by_number(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    (invoice,) = await list_templates(session, user_id=user_id, slug="invoice")
    numbered = await create_draft(session, user_id=user_id, template_id=invoice.id)
    await set_fields(
        session, user_id=user_id, document_id=numbered.id, values={"number": FieldValue("17")}
    )
    await create_draft(session, user_id=user_id, template_id=invoice.id)
    numbers = {
        summary.id: summary.number for summary in await list_documents(session, user_id=user_id)
    }
    assert numbers[numbered.id] == "17"
    assert None in numbers.values(), "у документа без номера номера нет"


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


async def test_counterparty_card_can_be_edited(session: AsyncSession) -> None:
    from core.usecases.documents import update_counterparty

    user_id = await make_user(session)
    card = await create_counterparty(session, user_id=user_id, name="Старое", values={})
    other = await create_counterparty(
        session, user_id=user_id, name="ООО «Клиент»", values={"inn": "500100732259"}
    )

    edited = await update_counterparty(
        session,
        user_id=user_id,
        counterparty_id=card.id,
        name="Новое",
        values={"inn": "7707083893"},
    )
    assert (edited.name, edited.inn) == ("Новое", "7707083893")
    with pytest.raises(ValidationError) as twin:
        await update_counterparty(
            session,
            user_id=user_id,
            counterparty_id=card.id,
            name="Новое",
            values={"inn": other.inn or ""},
        )
    assert twin.value.code == "counterparty.duplicate_inn"


def test_every_blank_fills_with_demo_requisites_without_errors() -> None:
    """Тестовые реквизиты сходятся в любом стандартном бланке, и готовый файл
    не содержит ни одного маркера: проверка БИК и счёта их не отвергает."""
    for template in BUILTIN_TEMPLATES:
        common = {"number": "17", "date": "28.09.2026", "city": "Москва", "total": "120 000"}
        keys = {spec.key for spec in template.fields}
        raw = {key: value for key, value in common.items() if key in keys}
        for spec in template.fields:
            for prefix, demo in (("seller_", DEMO_SELLER), ("client_", DEMO_CLIENT)):
                if spec.key.startswith(prefix) and spec.key.removeprefix(prefix) in demo:
                    raw[spec.key] = demo[spec.key.removeprefix(prefix)]
            if spec.key not in raw:
                raw[spec.key] = spec.default or {
                    FieldType.DATE: "31.10.2026",
                    FieldType.INTEGER: "10",
                    FieldType.MONEY: "1 000",
                }.get(spec.type, "значение")
        checked = validate_fields(
            template.fields, {key: FieldValue(value) for key, value in raw.items()}
        )
        assert checked.errors == () and checked.ready, (template.slug, checked.errors)
        filled = fill_docx(
            template.blank_bytes(),
            places=[],
            context=fill_context(template.fields, checked.values),
            blank="<пусто>",
        )
        # Линейки для подписей — часть бланка; пустых мест под данные не осталось.
        text = "\n".join(docx_lines(filled))
        assert "{{" not in text and "<пусто>" not in text, template.slug
