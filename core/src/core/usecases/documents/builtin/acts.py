"""Акт выполненных работ (оказанных услуг): закрывает счёт или договор.

Бланк сделан из бланка счёта — та же таблица позиций, итог, НДС и сумма
прописью, — поэтому акт по счёту переносит его позиции как есть, а акт по
договору получает одну строку: предмет и стоимость договора
(``core.usecases.documents.acts``). Подписывают обе стороны."""

from __future__ import annotations

from core.domain.documents import FieldType

from ._common import (
    BuiltinTemplate,
    client,
    date,
    director,
    items,
    number,
    seller,
    signer_position,
    subject,
)

ACT = BuiltinTemplate(
    slug="act",
    title="Акт выполненных работ",
    kind="act",
    description="Акт по счёту или договору: работы, сумма прописью, подписи обеих сторон.",
    blank="act.docx",
    fields=(
        number("Номер акта"),
        date("Дата акта"),
        seller("name", "Название исполнителя", FieldType.TEXT),
        seller("inn", "ИНН исполнителя", FieldType.INN),
        seller("address", "Адрес исполнителя", FieldType.ADDRESS, required=False),
        client("name", "Название заказчика", FieldType.TEXT),
        client("inn", "ИНН заказчика", FieldType.INN, required=False),
        client("address", "Адрес заказчика", FieldType.ADDRESS, required=False),
        subject(
            "basis",
            "Основание",
            FieldType.TEXT,
            required=False,
            hint="Договор № 17 от 01.08.2026 или Счёт № 5 от 03.10.2026",
        ),
        items(),
        subject(
            "vat",
            "НДС",
            FieldType.TEXT,
            required=False,
            default="Без НДС",
            hint="«Без НДС» или, например, «20% — 20 000,00»",
        ),
        signer_position(),
        seller("director", "Подписант исполнителя", FieldType.NAME, required=False),
        director("client"),
    ),
)

ACTS = (ACT,)
