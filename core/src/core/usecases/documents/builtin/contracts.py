"""Договоры оказания услуг: основной с заданием и актом и варианты под сторону сделки.

Варианты повторяют свои образцы: между юрлицами, между физлицами, с ИП и
с самозанятым на абонентское обслуживание, типовой с порядком приёмки и
претензиями. Пустые места типовых условий в образцах заполнены обычными
значениями (сроки приёмки, пени), всё, что меняется от сделки к сделке, — поля.
"""

from __future__ import annotations

from core.domain.documents import FieldType

from ._common import (
    BuiltinTemplate,
    basis,
    client,
    date,
    director,
    number,
    party,
    requisites,
    scope,
    seller,
    subject,
    total,
)

_CITY = subject("city", "Город", FieldType.TEXT)
_SUBJECT = subject(
    "subject", "Предмет договора", FieldType.MULTILINE, hint="Оказать услуги… по разработке сайта"
)
_ALL_REQUISITES = (
    "kpp",
    "ogrn",
    "address",
    "bank",
    "bic",
    "account",
    "corr_account",
    "phone",
    "email",
)
# Абонентские договоры с ИП и самозанятым сделаны по образцу юридических услуг:
# его состав услуг стоит значением по умолчанию, другой вид услуг — правкой поля.
_LEGAL_SUBJECT = subject(
    "subject",
    "Какие услуги",
    FieldType.TEXT,
    default="юридические услуги",
    hint="Оказывать… юридические услуги, бухгалтерские услуги",
)
_LEGAL_SCOPE = scope(
    default=(
        "- составление юридических документов (договоров, соглашений, справок, писем, "
        "обращений и т.д.);\n"
        "- правовая экспертиза документов Заказчика;\n"
        "- составление правовых заключений по вопросам Заказчика;\n"
        "- юридические консультации.\n"
        "Представление интересов Заказчика в судах всех инстанций, а также представление "
        "интересов в государственных органах производится на основании отдельно "
        "заключенного договора с выдачей доверенности."
    )
)
_MONTHLY = (
    subject("valid_until", "Договор заключён до", FieldType.DATE, carry_over=False),
    total("Стоимость услуг в месяц"),
    subject(
        "payment_day",
        "Оплата до какого числа месяца",
        FieldType.INTEGER,
        required=False,
        default="10",
    ),
)


SERVICE_CONTRACT = BuiltinTemplate(
    slug="service-contract",
    title="Договор оказания услуг",
    kind="contract",
    description="Договор возмездного оказания услуг с заданием и формой акта.",
    blank="contract.docx",
    fields=(
        number("Номер договора"),
        date("Дата договора", today=False),
        _CITY,
        *party("seller"),
        *requisites(
            "seller", "kpp", "ogrn", "address", "bank", "bic", "account", "corr_account", "email"
        ),
        director("seller", required=True),
        basis("seller"),
        *party("client"),
        *requisites(
            "client", "kpp", "ogrn", "address", "bank", "bic", "account", "corr_account", "email"
        ),
        director("client"),
        basis("client"),
        _SUBJECT,
        subject(
            "service_place",
            "Место оказания услуг",
            FieldType.TEXT,
            required=False,
            default="удалённо",
            hint="Адрес или «удалённо»",
        ),
        total(),
        subject(
            "vat",
            "НДС",
            FieldType.TEXT,
            required=False,
            default="не облагается",
            hint="«не облагается» или «в том числе НДС 20% — 20 000,00 руб.»",
        ),
        subject(
            "start",
            "Начало оказания услуг",
            FieldType.TEXT,
            required=False,
            default="со дня подписания Договора",
            hint="«со дня подписания Договора» или дата",
        ),
        subject("end_date", "Услуги оказать до", FieldType.DATE, carry_over=False),
        subject(
            "payment_days",
            "Срок оплаты после акта, рабочих дней",
            FieldType.INTEGER,
            required=False,
            default="5",
        ),
        subject(
            "valid_until", "Договор действует до", FieldType.DATE, required=False, carry_over=False
        ),
        subject(
            "requirements",
            "Требования к услугам и отчёту",
            FieldType.MULTILINE,
            required=False,
            default="в соответствии с Договором",
        ),
        subject(
            "client_materials",
            "Что передаёт заказчик",
            FieldType.MULTILINE,
            required=False,
            default="по запросу Исполнителя",
            hint="Сведения, документы и доступы для работы",
        ),
        subject(
            "expenses",
            "Возмещаемые расходы",
            FieldType.TEXT,
            required=False,
            default="не возмещаются",
        ),
    ),
)

CONTRACT_COMPANIES = BuiltinTemplate(
    slug="contract-companies",
    title="Договор оказания услуг: между юрлицами",
    kind="contract",
    description="Между организациями или с ИП: предмет, срок, цена, штраф и неустойка.",
    blank="contract-companies.docx",
    fields=(
        number("Номер договора"),
        date("Дата договора"),
        _CITY,
        *party("seller"),
        *requisites("seller", *_ALL_REQUISITES),
        director("seller"),
        basis("seller"),
        *party("client"),
        *requisites("client", *_ALL_REQUISITES),
        director("client"),
        basis("client"),
        _SUBJECT,
        scope(default="в соответствии с заданием Заказчика"),
        subject(
            "service_place",
            "Как оказываются услуги",
            FieldType.TEXT,
            required=False,
            default="удалённо",
            hint="Удалённо, по месту нахождения Заказчика",
        ),
        subject("term", "Срок оказания услуг", FieldType.TEXT, hint="до 30.11.2026"),
        total(),
        subject(
            "payment_term",
            "Срок оплаты после акта",
            FieldType.TEXT,
            required=False,
            default="5 (пяти) рабочих дней",
        ),
        subject(
            "exit_fee",
            "Компенсация за досрочный отказ, руб.",
            FieldType.MONEY,
            required=False,
        ),
        subject(
            "delay_fine",
            "Штраф за срыв срока, %",
            FieldType.TEXT,
            required=False,
            default="10",
        ),
        subject(
            "late_penalty",
            "Неустойка за просрочку оплаты, % в день",
            FieldType.TEXT,
            required=False,
            default="0,1",
        ),
        subject(
            "notice_channel",
            "Как направлять уведомления",
            FieldType.TEXT,
            required=False,
            default="направления заказным письмом или по электронной почте",
        ),
    ),
)


def _person(name: str) -> tuple:
    who = {"seller": "исполнителя", "client": "заказчика"}[name]
    make = seller if name == "seller" else client
    return (
        make("name", f"ФИО {who}", FieldType.NAME),
        make("birthdate", f"Дата рождения {who}", FieldType.DATE, required=False),
        make("address", f"Адрес {who}", FieldType.ADDRESS),
        make(
            "passport",
            f"Паспорт {who}",
            FieldType.TEXT,
            required=False,
            hint="Серия и номер: 45 01 123456",
        ),
        make(
            "passport_issued",
            f"Кем и когда выдан паспорт {who}",
            FieldType.TEXT,
            required=False,
        ),
        make("phone", f"Телефон {who}", FieldType.PHONE, required=False),
    )


CONTRACT_PERSONS = BuiltinTemplate(
    slug="contract-persons",
    title="Договор оказания услуг: между физлицами",
    kind="contract",
    description="Между гражданами: паспортные данные сторон, услуги, цена и срок.",
    blank="contract-persons.docx",
    fields=(
        date("Дата договора"),
        _CITY,
        *_person("client"),
        *_person("seller"),
        subject(
            "subject",
            "Какие услуги",
            FieldType.TEXT,
            hint="Предоставлять… юридические услуги, услуги репетитора",
        ),
        scope(),
        total(),
        subject("term", "Срок договора", FieldType.TEXT, hint="до 31.12.2026"),
        subject(
            "late_penalty",
            "Пени за просрочку оплаты",
            FieldType.TEXT,
            required=False,
            default="0,1%",
        ),
    ),
)

CONTRACT_IP = BuiltinTemplate(
    slug="contract-ip",
    title="Договор оказания услуг: с ИП",
    kind="contract",
    description="Абонентский договор с индивидуальным предпринимателем: оплата помесячно.",
    blank="contract-ip.docx",
    fields=(
        number("Номер договора"),
        date("Дата договора"),
        _CITY,
        seller(
            "name",
            "ИП исполнитель",
            FieldType.TEXT,
            hint="Индивидуальный предприниматель Петров Пётр Васильевич",
        ),
        seller("inn", "ИНН продавца", FieldType.INN),
        seller("ogrn", "ОГРНИП", FieldType.OGRN),
        seller(
            "director",
            "Подписант",
            FieldType.NAME,
            required=False,
            hint="Петров Пётр Васильевич",
        ),
        *requisites(
            "seller", "address", "bank", "bic", "account", "corr_account", "phone", "email"
        ),
        *party("client"),
        *requisites("client", *_ALL_REQUISITES),
        director("client"),
        basis("client"),
        _LEGAL_SUBJECT,
        _LEGAL_SCOPE,
        *_MONTHLY,
    ),
)

CONTRACT_SELF_EMPLOYED = BuiltinTemplate(
    slug="contract-self-employed",
    title="Договор оказания услуг: с самозанятым",
    kind="contract",
    description="Абонентский договор с плательщиком НПД: чек из «Мой налог», оплата помесячно.",
    blank="contract-self-employed.docx",
    fields=(
        number("Номер договора"),
        date("Дата договора"),
        _CITY,
        seller("name", "ФИО исполнителя", FieldType.NAME),
        seller("inn", "ИНН исполнителя", FieldType.INN),
        seller(
            "passport",
            "Паспорт исполнителя",
            FieldType.TEXT,
            required=False,
            hint="Серия и номер: 45 01 123456",
        ),
        seller(
            "passport_issued",
            "Кем и когда выдан паспорт",
            FieldType.TEXT,
            required=False,
        ),
        seller("email", "Почта исполнителя", FieldType.EMAIL, required=False),
        *party("client"),
        client("email", "Почта клиента", FieldType.EMAIL, required=False),
        director("client"),
        basis("client"),
        _LEGAL_SUBJECT,
        _LEGAL_SCOPE,
        *_MONTHLY,
    ),
)

CONTRACT_TYPICAL = BuiltinTemplate(
    slug="contract-typical",
    title="Договор оказания услуг: типовой",
    kind="contract",
    description="Подробный: приёмка по акту, недостатки, форс-мажор, претензионный порядок.",
    blank="contract-typical.docx",
    fields=(
        number("Номер договора"),
        date("Дата договора"),
        _CITY,
        *party("seller"),
        *requisites("seller", *_ALL_REQUISITES),
        director("seller"),
        basis("seller"),
        *party("client"),
        *requisites("client", *_ALL_REQUISITES),
        director("client"),
        basis("client"),
        _SUBJECT,
        subject("term", "Срок оказания услуг", FieldType.TEXT, hint="до 30.11.2026"),
        subject(
            "service_place",
            "Где оказываются услуги",
            FieldType.TEXT,
            required=False,
            default="по месту нахождения Исполнителя",
        ),
        subject(
            "requirements",
            "Требования к качеству",
            FieldType.TEXT,
            required=False,
            default="установленным законодательством Российской Федерации и Договором",
        ),
        total(),
        subject(
            "vat",
            "НДС",
            FieldType.TEXT,
            required=False,
            default="НДС не облагается",
            hint="«НДС не облагается» или «в том числе НДС 20% — 20 000,00 руб.»",
        ),
        subject(
            "payment_days",
            "Срок оплаты после акта, рабочих дней",
            FieldType.INTEGER,
            required=False,
            default="5",
        ),
        subject(
            "contract_term",
            "Договор действует в течение",
            FieldType.TEXT,
            required=False,
            default="одного года",
        ),
        subject(
            "attachments",
            "Приложения к договору",
            FieldType.TEXT,
            required=False,
            default="отсутствуют",
        ),
    ),
)

CONTRACTS = (
    SERVICE_CONTRACT,
    CONTRACT_COMPANIES,
    CONTRACT_PERSONS,
    CONTRACT_IP,
    CONTRACT_SELF_EMPLOYED,
    CONTRACT_TYPICAL,
)
