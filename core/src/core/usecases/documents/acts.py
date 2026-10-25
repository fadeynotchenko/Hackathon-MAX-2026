"""Акт по счёту или договору в один клик.

Акт закрывает уже подготовленный документ: стороны, подписанты и сумма в нём те
же. Поэтому акт создаётся из документа, а не с нуля: позиции счёта переходят
как есть, у договора и КП позиция одна — предмет и стоимость. Основание
(«Договор оказания услуг № 17 от 01.08.2026») пишется само. Значения переходят
со своим источником: подтверждённое в исходном документе не просит
подтверждения снова. Номер и дата — новые, как у любого нового документа.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.documents import (
    FieldType,
    FieldValue,
    Item,
    ValueSource,
    items_json,
    parse_money,
    render_context,
)
from core.domain.exceptions import AppError
from core.usecases.documents.builtin import ACT
from core.usecases.documents.drafts import DocumentView, create_draft, get_document, set_fields
from core.usecases.documents.templates import list_templates

# Из чего делается акт: то, что закрывают актом выполненных работ.
ACT_SOURCES = frozenset({"invoice", "contract", "offer"})
# Подставляется, если в договоре предмет не назван.
DEFAULT_ITEM_NAME = "Работы (услуги) по договору"
_CARRIED = (
    "seller_name",
    "seller_inn",
    "seller_address",
    "seller_position",
    "seller_director",
    "client_name",
    "client_inn",
    "client_address",
    "client_director",
    "vat",
)


def act_values(source: DocumentView) -> dict[str, FieldValue]:
    """Значения акта из исходного документа: стороны, позиции, основание."""
    values = {key: source.values[key] for key in _CARRIED if key in source.values}
    if "items" in source.values:
        values["items"] = source.values["items"]
    elif "total" in source.values:
        price = parse_money(source.values["total"].value)
        if price is not None and price > 0:
            name = next(
                (source.values[key].value for key in ("subject", "scope") if key in source.values),
                DEFAULT_ITEM_NAME,
            )
            line = Item(name=name.strip()[:1000], quantity=Decimal(1), unit="усл.", price=price)
            values["items"] = FieldValue(items_json([line]), source.values["total"].source)
    context = render_context(source.template.fields, source.values)
    basis = source.template.title
    if context.get("number"):
        basis += f" № {context['number']}"
    if context.get("date"):
        basis += f" от {context['date']}"
    values["basis"] = FieldValue(basis, ValueSource.DEFAULT)
    return values


async def create_act(session: AsyncSession, *, user_id: int, document_id: int) -> DocumentView:
    source = await get_document(session, user_id=user_id, document_id=document_id)
    if source.template.kind not in ACT_SOURCES:
        raise AppError(
            "Акт делается по счёту, договору или КП",
            code="act.unsupported",
            status_code=409,
        )
    templates = await list_templates(session, user_id=user_id, slug=ACT.slug)
    template = next((t for t in templates if t.is_builtin), None)
    if template is None:
        raise AppError("Шаблон акта не найден", code="act.template_missing", status_code=503)
    draft = await create_draft(
        session,
        user_id=user_id,
        template_id=template.id,
        counterparty_id=source.counterparty_id,
        organization_id=source.organization_id,
    )
    known = {spec.key for spec in template.fields if spec.type is not FieldType.ITEMS} | {"items"}
    carried = {key: value for key, value in act_values(source).items() if key in known}
    return await set_fields(session, user_id=user_id, document_id=draft.id, values=carried)
