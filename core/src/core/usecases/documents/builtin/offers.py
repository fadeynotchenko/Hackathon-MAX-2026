"""Коммерческие предложения: на бланке с реквизитами, краткое и с таблицей позиций."""

from __future__ import annotations

from core.domain.documents import FieldType

from ._common import (
    BuiltinTemplate,
    client,
    date,
    items,
    number,
    quantity,
    seller,
    signer_position,
    subject,
    vat_rate,
)

_SUBJECT = subject(
    "subject",
    "Тема предложения",
    FieldType.TEXT,
    hint="Что предлагаете: оказание услуг по разработке сайта",
)
_VALID_UNTIL = subject("valid_until", "Предложение действует до", FieldType.DATE, carry_over=False)
_DIRECTOR = seller("director", "Подписант", FieldType.NAME, required=False, hint="Иванов И. И.")
_CONTACT = seller(
    "contact", "Контактное лицо", FieldType.TEXT, required=False, hint="Должность, фамилия, имя"
)
_PAYMENT_TERMS = subject(
    "payment_terms",
    "Порядок оплаты",
    FieldType.TEXT,
    required=False,
    hint="Предоплата 50%, остаток — после сдачи работ",
)

OFFER = BuiltinTemplate(
    slug="offer",
    title="Коммерческое предложение",
    kind="offer",
    description="Предложение клиенту: состав работ, сумма прописью, условия и срок действия.",
    blank="offer.docx",
    fields=(
        date("Дата предложения", today=False),
        number("Исходящий номер", required=False),
        seller("name", "Название продавца", FieldType.TEXT),
        seller("inn", "ИНН продавца", FieldType.INN, required=False),
        seller("ogrn", "ОГРН продавца", FieldType.OGRN, required=False),
        seller("address", "Адрес продавца", FieldType.ADDRESS, required=False),
        seller("phone", "Телефон", FieldType.PHONE, required=False),
        seller("email", "Почта", FieldType.EMAIL, required=False),
        seller("site", "Сайт", FieldType.TEXT, required=False),
        client(
            "recipient_position",
            "Должность получателя",
            FieldType.TEXT,
            required=False,
            hint="Кому: Генеральному директору",
        ),
        client("name", "Название клиента", FieldType.TEXT),
        client(
            "recipient",
            "Получатель",
            FieldType.TEXT,
            required=False,
            hint="Кому: Петрову Петру Петровичу",
        ),
        client(
            "greeting",
            "Обращение",
            FieldType.TEXT,
            required=False,
            hint="Имя и отчество: Пётр Петрович",
        ),
        _SUBJECT,
        subject("scope", "Состав работ", FieldType.MULTILINE),
        *quantity(),
        subject("total", "Стоимость", FieldType.MONEY),
        subject(
            "vat",
            "НДС",
            FieldType.TEXT,
            required=False,
            default="не облагается",
            hint="«не облагается» или «20% — 20 000,00 руб.»",
        ),
        _PAYMENT_TERMS,
        subject("term", "Срок выполнения", FieldType.TEXT, required=False),
        subject("delivery", "Доставка", FieldType.TEXT, required=False),
        subject("warranty", "Гарантия", FieldType.TEXT, required=False),
        _VALID_UNTIL,
        _CONTACT,
        signer_position(),
        _DIRECTOR,
    ),
)

OFFER_SHORT = BuiltinTemplate(
    slug="offer-short",
    title="Коммерческое предложение: краткое",
    kind="offer",
    description="Одна страница: кому, что предлагаете, таблица с ценой и срок действия.",
    blank="offer-short.docx",
    fields=(
        seller("name", "Название продавца", FieldType.TEXT),
        seller("inn", "ИНН продавца", FieldType.INN, required=False),
        seller("address", "Адрес продавца", FieldType.ADDRESS, required=False),
        seller("phone", "Телефон", FieldType.PHONE, required=False),
        client(
            "recipient",
            "Кому",
            FieldType.TEXT,
            required=False,
            hint="Генеральному директору Петрову П. П.",
        ),
        client("name", "Название клиента", FieldType.TEXT),
        subject(
            "subject",
            "Что предлагаете",
            FieldType.TEXT,
            hint="Поставку оборудования, оказание услуг по разработке сайта",
        ),
        subject("scope", "Наименование в таблице", FieldType.MULTILINE),
        *quantity(),
        subject("total", "Стоимость", FieldType.MONEY),
        _VALID_UNTIL,
        signer_position(),
        _DIRECTOR,
        _CONTACT,
    ),
)

OFFER_ITEMS = BuiltinTemplate(
    slug="offer-items",
    title="Коммерческое предложение: с позициями",
    kind="offer",
    description="Номенклатура с ценой с НДС, сроком поставки, изготовителем и характеристиками.",
    blank="offer-items.docx",
    fields=(
        number("Номер предложения", required=False),
        date("Дата предложения"),
        seller("name", "Название продавца", FieldType.TEXT),
        seller("inn", "ИНН продавца", FieldType.INN, required=False),
        client("name", "Название клиента", FieldType.TEXT),
        items(unit="шт."),
        subject("delivery_term", "Срок поставки", FieldType.TEXT, required=False),
        subject("manufacturer", "Изготовитель / страна", FieldType.TEXT, required=False),
        subject("specs", "Характеристики", FieldType.MULTILINE, required=False),
        vat_rate(),
        _PAYMENT_TERMS,
        _VALID_UNTIL,
        subject("extra_terms", "Дополнительные условия", FieldType.TEXT, required=False),
        subject("attachments", "Приложения", FieldType.TEXT, required=False, default="нет"),
        signer_position(),
        _DIRECTOR,
    ),
)

OFFERS = (OFFER, OFFER_SHORT, OFFER_ITEMS)
