"""Счета: стандартный (банк получателя и сумма прописью), на товар и с НДС по ставке.

Строк в таблице счёта сколько угодно (поле ``items``): итог, «Всего наименований»
и сумма прописью считаются из позиций. Прошлая редакция — одно наименование и
сумма на всё (``item`` + ``total``) — осталась у документов, сделанных до неё,
а копия такого счёта переносит его строку в позиции (``legacy_items``)."""

from __future__ import annotations

from core.domain.documents import FieldType

from ._common import (
    BuiltinTemplate,
    client,
    date,
    items,
    number,
    seller,
    signer_position,
    subject,
    vat_rate,
)

_BANK = (
    seller("bank", "Банк", FieldType.TEXT),
    seller("bic", "БИК", FieldType.BIC),
    seller("account", "Расчётный счёт", FieldType.ACCOUNT),
    seller("corr_account", "Корр. счёт банка", FieldType.ACCOUNT, required=False),
)
_SELLER = (
    seller("name", "Название продавца", FieldType.TEXT),
    seller("inn", "ИНН продавца", FieldType.INN),
    seller("kpp", "КПП продавца", FieldType.KPP, required=False),
    seller("address", "Адрес продавца", FieldType.ADDRESS, required=False),
)
_CLIENT = (
    client("name", "Название клиента", FieldType.TEXT),
    client("inn", "ИНН клиента", FieldType.INN, required=False),
)
_SIGNERS = (
    seller("director", "Подписант", FieldType.NAME, required=False, hint="Иванов И. И."),
    seller(
        "accountant",
        "Главный бухгалтер",
        FieldType.NAME,
        required=False,
        hint="Если его нет — оставьте пустым",
    ),
)
_VAT_TEXT = subject(
    "vat",
    "НДС",
    FieldType.TEXT,
    required=False,
    default="Без НДС",
    hint="«Без НДС» или, например, «20% — 20 000,00»",
)


def _invoice_fields(*, unit: str, position: bool = True) -> tuple:
    return (
        number("Номер счёта"),
        date("Дата счёта"),
        *_SELLER,
        *_BANK,
        *_CLIENT,
        client("address", "Адрес клиента", FieldType.ADDRESS, required=False),
        items(unit=unit),
        _VAT_TEXT,
        *((signer_position(),) if position else ()),
        *_SIGNERS,
    )


INVOICE = BuiltinTemplate(
    slug="invoice",
    title="Счёт на оплату",
    kind="invoice",
    description="Счёт с банком получателя, позициями, НДС и суммой прописью.",
    blank="invoice.docx",
    fields=_invoice_fields(unit="усл."),
)

INVOICE_GOODS = BuiltinTemplate(
    slug="invoice-goods",
    title="Счёт на оплату: товар",
    kind="invoice",
    description="Счёт на товар с условиями отпуска: оплата — согласие с условиями поставки.",
    blank="invoice-goods.docx",
    fields=(
        # Подписи в образце — одной строкой, без должности.
        *_invoice_fields(unit="шт.", position=False),
        subject(
            "payment_note",
            "Условия отпуска товара",
            FieldType.MULTILINE,
            required=False,
            default=(
                "Внимание! Оплата данного счета означает согласие с условиями поставки "
                "товара. Уведомление об оплате обязательно, в противном случае не "
                "гарантируется наличие товара на складе. Товар отпускается по факту прихода "
                "денег на р/с Поставщика, самовывозом, при наличии доверенности и паспорта."
            ),
        ),
    ),
)

INVOICE_VAT = BuiltinTemplate(
    slug="invoice-vat",
    title="Счёт на оплату: с НДС и основанием",
    kind="invoice",
    description="Анкетный счёт: поставщик, покупатель, основание, НДС по ставке в том числе.",
    blank="invoice-vat.docx",
    fields=(
        number("Номер счёта"),
        date("Дата счёта"),
        *_SELLER,
        seller("bank", "Банк", FieldType.TEXT),
        seller("account", "Расчётный счёт", FieldType.ACCOUNT),
        seller("corr_account", "Корр. счёт банка", FieldType.ACCOUNT, required=False),
        seller("bic", "БИК", FieldType.BIC),
        *_CLIENT,
        client("kpp", "КПП клиента", FieldType.KPP, required=False),
        client("address", "Адрес клиента", FieldType.ADDRESS, required=False),
        subject(
            "basis",
            "Основание",
            FieldType.TEXT,
            required=False,
            hint="Договор поставки от 01.08.2026 № 17",
        ),
        items(),
        vat_rate(),
        *_SIGNERS,
    ),
)

INVOICES = (INVOICE, INVOICE_GOODS, INVOICE_VAT)
