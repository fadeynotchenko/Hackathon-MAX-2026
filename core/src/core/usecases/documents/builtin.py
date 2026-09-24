"""Встроенные шаблоны: то, с чем продукт открывается у нового пользователя.

Тело шаблона — текст с маркерами ``{{key}}``. Формат ``text`` временный:
как только появится рендер DOCX, тело переедет в файл, а спецификация полей
останется той же.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.domain.documents import FieldSpec, FieldType

SELLER = "Продавец"
CLIENT = "Клиент"
SUBJECT = "Предмет"


@dataclass(frozen=True)
class BuiltinTemplate:
    slug: str
    title: str
    kind: str
    description: str
    fields: tuple[FieldSpec, ...]
    body: str


_SELLER_REQUISITES = (
    FieldSpec("seller_name", "Название продавца", FieldType.TEXT, group=SELLER),
    FieldSpec("seller_inn", "ИНН продавца", FieldType.INN, group=SELLER),
    FieldSpec("seller_kpp", "КПП продавца", FieldType.KPP, required=False, group=SELLER),
    FieldSpec("seller_address", "Адрес продавца", FieldType.ADDRESS, required=False, group=SELLER),
)
_BANK_REQUISITES = (
    FieldSpec("seller_bank", "Банк", FieldType.TEXT, group=SELLER),
    FieldSpec("seller_bic", "БИК", FieldType.BIC, group=SELLER),
    FieldSpec("seller_account", "Расчётный счёт", FieldType.ACCOUNT, group=SELLER),
)

INVOICE = BuiltinTemplate(
    slug="invoice",
    title="Счёт на оплату",
    kind="invoice",
    description="Счёт с реквизитами продавца, банком и суммой к оплате.",
    fields=(
        FieldSpec(
            "number",
            "Номер счёта",
            FieldType.TEXT,
            group=SUBJECT,
            max_length=32,
            carry_over=False,
        ),
        FieldSpec(
            "date",
            "Дата счёта",
            FieldType.DATE,
            group=SUBJECT,
            carry_over=False,
            today_by_default=True,
        ),
        *_SELLER_REQUISITES,
        *_BANK_REQUISITES,
        FieldSpec("client_name", "Название клиента", FieldType.TEXT, group=CLIENT),
        FieldSpec("client_inn", "ИНН клиента", FieldType.INN, required=False, group=CLIENT),
        FieldSpec(
            "client_address", "Адрес клиента", FieldType.ADDRESS, required=False, group=CLIENT
        ),
        FieldSpec("item", "Наименование работ или услуг", FieldType.MULTILINE, group=SUBJECT),
        FieldSpec("total", "Сумма к оплате", FieldType.MONEY, group=SUBJECT),
        FieldSpec(
            "vat",
            "НДС",
            FieldType.TEXT,
            required=False,
            group=SUBJECT,
            hint="«Без НДС» или, например, «20% — 20 000,00»",
        ),
        FieldSpec(
            "due_date",
            "Оплатить до",
            FieldType.DATE,
            required=False,
            group=SUBJECT,
            carry_over=False,
        ),
        FieldSpec("seller_director", "Подписант", FieldType.NAME, required=False, group=SELLER),
    ),
    body="""Счёт на оплату № {{number}} от {{date}}

Поставщик: {{seller_name}}, ИНН {{seller_inn}}, КПП {{seller_kpp}}
Адрес: {{seller_address}}
Банк: {{seller_bank}}, БИК {{seller_bic}}, расчётный счёт {{seller_account}}

Покупатель: {{client_name}}, ИНН {{client_inn}}
Адрес: {{client_address}}

Предмет счёта:
{{item}}

Сумма к оплате: {{total}} руб.
НДС: {{vat}}
Оплатить до: {{due_date}}

Руководитель ______________________ / {{seller_director}} /
""",
)

OFFER = BuiltinTemplate(
    slug="offer",
    title="Коммерческое предложение",
    kind="offer",
    description="Предложение клиенту: состав работ, сумма и срок действия.",
    fields=(
        FieldSpec("date", "Дата предложения", FieldType.DATE, group=SUBJECT, carry_over=False),
        FieldSpec("seller_name", "Название продавца", FieldType.TEXT, group=SELLER),
        FieldSpec("seller_phone", "Телефон", FieldType.PHONE, required=False, group=SELLER),
        FieldSpec("seller_email", "Почта", FieldType.EMAIL, required=False, group=SELLER),
        FieldSpec("client_name", "Название клиента", FieldType.TEXT, group=CLIENT),
        FieldSpec("subject", "Тема предложения", FieldType.TEXT, group=SUBJECT),
        FieldSpec("scope", "Состав работ", FieldType.MULTILINE, group=SUBJECT),
        FieldSpec("total", "Стоимость", FieldType.MONEY, group=SUBJECT),
        FieldSpec("term", "Срок выполнения", FieldType.TEXT, required=False, group=SUBJECT),
        FieldSpec(
            "valid_until",
            "Предложение действует до",
            FieldType.DATE,
            group=SUBJECT,
            carry_over=False,
        ),
    ),
    body="""Коммерческое предложение от {{date}}

Кому: {{client_name}}
От кого: {{seller_name}}

Тема: {{subject}}

Состав работ:
{{scope}}

Стоимость: {{total}} руб.
Срок выполнения: {{term}}
Предложение действует до {{valid_until}}.

Связаться: {{seller_phone}}, {{seller_email}}
""",
)

SERVICE_CONTRACT = BuiltinTemplate(
    slug="service-contract",
    title="Договор оказания услуг",
    kind="contract",
    description="Рамочный договор услуг: стороны, предмет, стоимость и срок.",
    fields=(
        FieldSpec(
            "number",
            "Номер договора",
            FieldType.TEXT,
            group=SUBJECT,
            max_length=32,
            carry_over=False,
        ),
        FieldSpec("date", "Дата договора", FieldType.DATE, group=SUBJECT, carry_over=False),
        FieldSpec("city", "Город", FieldType.TEXT, group=SUBJECT),
        *_SELLER_REQUISITES,
        FieldSpec("seller_director", "Подписант продавца", FieldType.NAME, group=SELLER),
        FieldSpec("client_name", "Название клиента", FieldType.TEXT, group=CLIENT),
        FieldSpec("client_inn", "ИНН клиента", FieldType.INN, group=CLIENT),
        FieldSpec(
            "client_director", "Подписант клиента", FieldType.NAME, required=False, group=CLIENT
        ),
        FieldSpec("subject", "Предмет договора", FieldType.MULTILINE, group=SUBJECT),
        FieldSpec("total", "Стоимость услуг", FieldType.MONEY, group=SUBJECT),
        FieldSpec("term_days", "Срок оказания, дней", FieldType.INTEGER, group=SUBJECT),
        FieldSpec(
            "payment_days", "Срок оплаты, дней", FieldType.INTEGER, required=False, group=SUBJECT
        ),
    ),
    body="""Договор оказания услуг № {{number}}

{{city}}, {{date}}

{{seller_name}} (ИНН {{seller_inn}}), именуемое «Исполнитель», в лице {{seller_director}}, и {{client_name}} (ИНН {{client_inn}}), именуемое «Заказчик», в лице {{client_director}}, заключили настоящий договор.

1. Предмет договора
{{subject}}

2. Стоимость и порядок расчётов
2.1. Стоимость услуг составляет {{total}} руб.
2.2. Заказчик оплачивает услуги в течение {{payment_days}} дней с момента подписания акта.

3. Срок
3.1. Исполнитель оказывает услуги в течение {{term_days}} дней с даты подписания договора.

4. Реквизиты и подписи сторон
Исполнитель: {{seller_name}}, адрес {{seller_address}}
Заказчик: {{client_name}}

Исполнитель ______________________ / {{seller_director}} /
Заказчик ______________________ / {{client_director}} /
""",
)

BUILTIN_TEMPLATES: tuple[BuiltinTemplate, ...] = (INVOICE, OFFER, SERVICE_CONTRACT)
