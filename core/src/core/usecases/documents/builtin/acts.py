"""Акты: закрывают счёт или договор и фиксируют передачу имущества.

Основной акт сделан из бланка счёта — та же таблица позиций, итог, НДС и сумма
прописью, — поэтому акт по счёту переносит его позиции как есть, а акт по
договору получает одну строку: предмет и стоимость договора
(``core.usecases.documents.acts``). Подписывают обе стороны.

Остальные — по образцам владельца продукта: акт об оказании услуг между
организациями, акт сдачи-приёма услуг исполнителя-ИП или самозанятого и акт
приёма-передачи имущества между гражданами по договору купли-продажи."""

from __future__ import annotations

from core.domain.documents import FieldSpec, FieldType

from ._common import (
    BuiltinTemplate,
    basis,
    client,
    date,
    director,
    items,
    number,
    seller,
    signer_position,
    subject,
    vat_rate,
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

_CONTRACT_NUMBER = subject("contract_number", "Номер договора", FieldType.TEXT, required=False)
_CONTRACT_DATE = subject("contract_date", "Дата договора", FieldType.DATE, required=False)
_VAT_TEXT = subject(
    "vat",
    "НДС",
    FieldType.TEXT,
    required=False,
    default="без НДС",
    hint="«без НДС» или, например, «20%»",
)


def _client_position(hint: str) -> FieldSpec:
    return client("position", "Должность подписанта заказчика", FieldType.TEXT, hint=hint)


ACT_SERVICES = BuiltinTemplate(
    slug="act-services",
    title="Акт об оказании услуг",
    kind="act",
    description="Между организациями: работы с ценой и НДС, приложение к договору.",
    blank="act-services.docx",
    fields=(
        number("Номер акта"),
        date("Дата акта"),
        seller("name", "Название исполнителя", FieldType.TEXT),
        seller(
            "position",
            "Должность подписанта исполнителя",
            FieldType.TEXT,
            required=False,
            default="директор",
        ),
        seller("director", "Подписант исполнителя", FieldType.NAME, hint="Иванов И. И."),
        client("name", "Название заказчика", FieldType.TEXT),
        _client_position("директор"),
        director("client", required=True),
        items(),
        _VAT_TEXT,
        _CONTRACT_NUMBER,
        _CONTRACT_DATE,
    ),
)

ACT_ACCEPTANCE = BuiltinTemplate(
    slug="act-acceptance",
    title="Акт сдачи-приёма услуг: исполнитель ИП",
    kind="act",
    description="Заказчик — организация, исполнитель — ИП или самозанятый; услуги с НДС по ставке.",
    blank="act-acceptance.docx",
    fields=(
        number("Номер акта"),
        date("Дата акта"),
        subject("city", "Город", FieldType.TEXT),
        client("name", "Название заказчика", FieldType.TEXT),
        # В бланке: «в лице генерального директора Петрова…» — родительный падеж.
        _client_position("генерального директора"),
        director("client", required=True),
        basis("client"),
        seller("name", "ФИО исполнителя", FieldType.NAME, hint="ИП Иванов Иван Иванович"),
        seller(
            "position",
            "Кто исполнитель",
            FieldType.TEXT,
            required=False,
            default="Индивидуальный предприниматель",
            hint="Индивидуальный предприниматель или самозанятый",
        ),
        seller("director", "Подпись исполнителя", FieldType.NAME, hint="Иванов И. И."),
        _CONTRACT_DATE,
        _CONTRACT_NUMBER,
        items(),
        vat_rate(),
    ),
)


def _person(name: str, role: str) -> tuple[FieldSpec, ...]:
    make = seller if name == "seller" else client
    return (
        make("name", f"ФИО {role}", FieldType.NAME),
        make("birthdate", f"Дата рождения {role}", FieldType.DATE, required=False),
        make("address", f"Адрес регистрации {role}", FieldType.ADDRESS),
        make(
            "passport",
            f"Паспорт {role}",
            FieldType.TEXT,
            required=False,
            hint="Серия и номер: 45 01 123456",
        ),
        make(
            "passport_issued", f"Кем и когда выдан паспорт {role}", FieldType.TEXT, required=False
        ),
    )


ACT_TRANSFER = BuiltinTemplate(
    slug="act-transfer",
    title="Акт приёма-передачи имущества",
    kind="act",
    description="Между гражданами по договору купли-продажи: что передано, паспорта сторон.",
    blank="act-transfer.docx",
    fields=(
        date("Дата акта"),
        subject("city", "Город", FieldType.TEXT),
        *_person("seller", "продавца"),
        *_person("client", "покупателя"),
        _CONTRACT_DATE,
        subject(
            "object",
            "Что передаётся",
            FieldType.MULTILINE,
            hint="машино-место № 92 по адресу: Москва, Малый Конаковский пер., д. 2, кадастровый № …",
        ),
    ),
)

ACTS = (ACT, ACT_SERVICES, ACT_ACCEPTANCE, ACT_TRANSFER)
