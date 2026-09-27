"""Свои шаблоны: сохранить, заполнить как встроенный, править и удалять,
не ломая документы, уже созданные на шаблоне."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import TemplateRepository
from core.domain.documents import FieldSpec, FieldType, FieldValue, ValueSource
from core.domain.exceptions import ForbiddenError, NotFoundError, ValidationError
from core.usecases.documents import (
    TemplateInput,
    copy_document,
    create_counterparty,
    create_draft,
    create_organization,
    create_template,
    delete_template,
    ensure_builtin_templates,
    get_document,
    get_template,
    list_templates,
    set_fields,
    update_template,
)
from core.usecases.documents.templates import CUSTOM_KIND, OWN_TEMPLATES_MAX
from tests.usecases.test_documents import make_user

ACT_BODY = """Акт № {{number}} от {{date}}

Исполнитель: {{seller_name}}, ИНН {{seller_inn}}
Заказчик: {{client_name}}, ИНН {{client_inn}}

Работы: {{works}}
Стоимость: {{total}} руб."""

ACT_FIELDS = (
    FieldSpec("number", "Номер акта", FieldType.TEXT, carry_over=False),
    FieldSpec("date", "Дата акта", FieldType.DATE, carry_over=False, today_by_default=True),
    FieldSpec("seller_name", "Название продавца"),
    FieldSpec("seller_inn", "ИНН продавца", FieldType.INN),
    FieldSpec("client_name", "Название клиента"),
    # Клиент прислал ИНН текстом: реквизит всё равно проверяется как ИНН.
    FieldSpec("client_inn", "ИНН клиента", FieldType.TEXT, required=False),
    FieldSpec("works", "Выполненные работы", FieldType.MULTILINE),
    FieldSpec("total", "Стоимость", FieldType.MONEY),
)


def act(**overrides: object) -> TemplateInput:
    data: dict[str, object] = {
        "title": "Акт выполненных работ",
        "description": "Акт к договору услуг",
        "body": ACT_BODY,
        "fields": ACT_FIELDS,
    }
    return TemplateInput(**(data | overrides))  # type: ignore[arg-type]


async def test_own_template_is_saved_and_fills_like_a_builtin(session: AsyncSession) -> None:
    user_id = await make_user(session)
    await ensure_builtin_templates(session)
    await create_organization(
        session, user_id=user_id, name="ООО «Ромашка»", values={"inn": "7707083893"}
    )
    client = await create_counterparty(
        session, user_id=user_id, name="ООО «Клиент»", values={"inn": "500100732259"}
    )

    saved = await create_template(session, user_id=user_id, data=act(title="  Акт  "))

    assert saved.title == "Акт" and saved.kind == CUSTOM_KIND and not saved.is_builtin
    assert saved.slug.startswith("my-")
    fields = {spec.key: spec for spec in saved.fields}
    assert fields["client_inn"].type is FieldType.INN
    assert (fields["seller_inn"].group, fields["client_name"].group, fields["works"].group) == (
        "Продавец",
        "Клиент",
        "Предмет",
    )
    library = await list_templates(session, user_id=user_id)
    assert [t.id for t in library][-1] == saved.id, "свои шаблоны — после стандартных"

    document = await create_draft(
        session, user_id=user_id, template_id=saved.id, counterparty_id=client.id
    )
    assert document.values["seller_inn"].source is ValueSource.PROFILE
    assert document.values["client_inn"].value == "500100732259"
    assert document.values["date"].source is ValueSource.DEFAULT
    assert set(document.missing) == {"number", "works", "total"}

    bad = await set_fields(
        session,
        user_id=user_id,
        document_id=document.id,
        values={"client_inn": FieldValue("1234567890")},
    )
    assert [e.code for e in bad.errors] == ["field.inn_invalid"]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (act(title=" "), "Назовите шаблон"),
        (act(body=""), "Напишите текст шаблона"),
        (act(body=ACT_BODY + "\nСрок: {{term}}"), "поле {{term}}, которого нет в списке полей"),
        (act(fields=(*ACT_FIELDS, FieldSpec("vat", "НДС"))), "«НДС» не встречается в тексте"),
        (
            act(
                body="Текст {{a}} и {{b}}",
                fields=(FieldSpec("a", "Сумма"), FieldSpec("b", "сумма")),
            ),
            "Два поля называются «сумма»",
        ),
        (act(body="Просто текст", fields=()), "хотя бы одно поле"),
        (act(body="{{Сумма}}", fields=()), "поле {{Сумма}}"),
    ],
)
async def test_template_is_checked_before_saving(
    session: AsyncSession, data: TemplateInput, message: str
) -> None:
    user_id = await make_user(session)
    with pytest.raises(ValidationError) as error:
        await create_template(session, user_id=user_id, data=data)
    assert error.value.code == "template.invalid"
    assert message in error.value.public_message


async def test_edit_keeps_existing_documents_on_the_old_text(session: AsyncSession) -> None:
    user_id = await make_user(session)
    saved = await create_template(session, user_id=user_id, data=act())
    old = await create_draft(session, user_id=user_id, template_id=saved.id)
    await set_fields(
        session, user_id=user_id, document_id=old.id, values={"works": FieldValue("Вёрстка")}
    )

    edited = await update_template(
        session,
        user_id=user_id,
        template_id=saved.id,
        data=act(
            title="Акт сдачи-приёмки",
            body="АКТ СДАЧИ-ПРИЁМКИ\nЗаказчик: {{client_name}}\nПринято: {{works}}",
            fields=(FieldSpec("client_name", "Название клиента"), ACT_FIELDS[6]),
        ),
    )

    assert (edited.id, edited.slug) == (saved.id, saved.slug), "ссылки и кнопки ведут туда же"
    assert edited.title == "Акт сдачи-приёмки"
    reloaded = await get_document(session, user_id=user_id, document_id=old.id)
    assert reloaded.preview.startswith("Акт № "), "созданный документ не меняет текст"
    assert reloaded.errors == ()
    assert [t.title for t in await list_templates(session, user_id=user_id)] == [
        "Акт сдачи-приёмки"
    ], "прошлая редакция в библиотеке не видна"

    fresh = await create_draft(session, user_id=user_id, template_id=saved.id)
    assert fresh.preview.startswith("АКТ СДАЧИ-ПРИЁМКИ")
    copy = await copy_document(session, user_id=user_id, document_id=old.id)
    assert copy.template.id == saved.id, "копия берёт новую редакцию"
    assert copy.values["works"].value == "Вёрстка"


async def test_edit_without_documents_changes_template_in_place(session: AsyncSession) -> None:
    user_id = await make_user(session)
    saved = await create_template(session, user_id=user_id, data=act())
    await update_template(
        session, user_id=user_id, template_id=saved.id, data=act(description="Новое")
    )
    repo = TemplateRepository(session)
    assert await repo.count_owned(user_id) == 1
    assert (await get_template(session, user_id=user_id, template_id=saved.id)).description == (
        "Новое"
    )


async def test_delete_hides_template_but_keeps_its_documents(session: AsyncSession) -> None:
    user_id = await make_user(session)
    used = await create_template(session, user_id=user_id, data=act())
    unused = await create_template(session, user_id=user_id, data=act(title="Черновой"))
    document = await create_draft(session, user_id=user_id, template_id=used.id)

    await delete_template(session, user_id=user_id, template_id=used.id)
    await delete_template(session, user_id=user_id, template_id=unused.id)

    assert await list_templates(session, user_id=user_id) == []
    assert await TemplateRepository(session).get(unused.id) is None
    reloaded = await get_document(session, user_id=user_id, document_id=document.id)
    assert reloaded.template.id == used.id and reloaded.preview.startswith("Акт")
    with pytest.raises(NotFoundError):
        await create_draft(session, user_id=user_id, template_id=used.id)
    with pytest.raises(NotFoundError):
        await get_template(session, user_id=user_id, template_id=used.id)


async def test_builtin_and_foreign_templates_are_read_only(session: AsyncSession) -> None:
    owner_id = await make_user(session, max_user_id=1)
    stranger_id = await make_user(session, max_user_id=2)
    await ensure_builtin_templates(session)
    (invoice,) = await list_templates(session, user_id=owner_id, slug="invoice")
    own = await create_template(session, user_id=owner_id, data=act())

    with pytest.raises(ForbiddenError):
        await update_template(session, user_id=owner_id, template_id=invoice.id, data=act())
    with pytest.raises(ForbiddenError):
        await delete_template(session, user_id=owner_id, template_id=invoice.id)
    with pytest.raises(NotFoundError):
        await get_template(session, user_id=stranger_id, template_id=own.id)
    with pytest.raises(NotFoundError):
        await update_template(session, user_id=stranger_id, template_id=own.id, data=act())
    with pytest.raises(NotFoundError):
        await delete_template(session, user_id=stranger_id, template_id=own.id)
    assert own.id not in {t.id for t in await list_templates(session, user_id=stranger_id)}


async def test_own_templates_are_limited(session: AsyncSession) -> None:
    user_id = await make_user(session)
    for index in range(OWN_TEMPLATES_MAX):
        await create_template(session, user_id=user_id, data=act(title=f"Акт {index}"))
    with pytest.raises(ValidationError) as error:
        await create_template(session, user_id=user_id, data=act())
    assert error.value.code == "template.limit"
