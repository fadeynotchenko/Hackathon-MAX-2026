"""Встроенные шаблоны: то, с чем продукт открывается у нового пользователя.

Тело шаблона — файл-бланк DOCX из ``blanks/``: счёт, КП и договор, сделанные по
образцам делового оборота («рыбам»). Места для данных в бланке размечены
маркерами ``{{key}}`` прямо в тексте файла, поэтому бланк правится в Word без
кода: маркер — это поле ниже. ``{{key|вариант}}`` — то же значение в другой
записи: сумма прописью, дата словами (``core.domain.documents.fill_context``).
Документ собирается в копии бланка, и PDF получается из неё же — с таблицами,
линейками и шрифтами образца.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

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
    # Файл бланка в ``blanks/``.
    blank: str

    def blank_bytes(self) -> bytes:
        return files(__package__).joinpath("blanks", self.blank).read_bytes()


def _seller(key: str, label: str, field_type: FieldType, **extra: object) -> FieldSpec:
    return FieldSpec(f"seller_{key}", label, field_type, group=SELLER, **extra)  # type: ignore[arg-type]


def _client(key: str, label: str, field_type: FieldType, **extra: object) -> FieldSpec:
    return FieldSpec(f"client_{key}", label, field_type, group=CLIENT, **extra)  # type: ignore[arg-type]


def _subject(key: str, label: str, field_type: FieldType, **extra: object) -> FieldSpec:
    return FieldSpec(key, label, field_type, group=SUBJECT, **extra)  # type: ignore[arg-type]


def _number(label: str, *, required: bool = True) -> FieldSpec:
    return _subject(
        "number", label, FieldType.TEXT, required=required, max_length=32, carry_over=False
    )


_BANK = (
    _seller("bank", "Банк", FieldType.TEXT),
    _seller("bic", "БИК", FieldType.BIC),
    _seller("account", "Расчётный счёт", FieldType.ACCOUNT),
    _seller("corr_account", "Корр. счёт банка", FieldType.ACCOUNT, required=False),
)
# Одна строка на весь предмет: количество и единица — для цены за единицу.
_QUANTITY = (
    _subject("quantity", "Количество", FieldType.INTEGER, required=False, default="1"),
    _subject(
        "unit", "Единица", FieldType.TEXT, required=False, default="усл.", hint="усл., шт., ч"
    ),
)
_SIGNER_POSITION = _seller(
    "position",
    "Должность подписанта",
    FieldType.TEXT,
    required=False,
    hint="Генеральный директор, Индивидуальный предприниматель",
)

INVOICE = BuiltinTemplate(
    slug="invoice",
    title="Счёт на оплату",
    kind="invoice",
    description="Счёт с банком получателя, позицией, НДС и суммой прописью.",
    blank="invoice.docx",
    fields=(
        _number("Номер счёта"),
        _subject("date", "Дата счёта", FieldType.DATE, carry_over=False, today_by_default=True),
        _seller("name", "Название продавца", FieldType.TEXT),
        _seller("inn", "ИНН продавца", FieldType.INN),
        _seller("kpp", "КПП продавца", FieldType.KPP, required=False),
        _seller("address", "Адрес продавца", FieldType.ADDRESS, required=False),
        *_BANK,
        _client("name", "Название клиента", FieldType.TEXT),
        _client("inn", "ИНН клиента", FieldType.INN, required=False),
        _client("address", "Адрес клиента", FieldType.ADDRESS, required=False),
        _subject("item", "Наименование работ или услуг", FieldType.MULTILINE),
        *_QUANTITY,
        _subject("total", "Сумма к оплате", FieldType.MONEY),
        _subject(
            "vat",
            "НДС",
            FieldType.TEXT,
            required=False,
            default="Без НДС",
            hint="«Без НДС» или, например, «20% — 20 000,00»",
        ),
        _SIGNER_POSITION,
        _seller("director", "Подписант", FieldType.NAME, required=False, hint="Иванов И. И."),
        _seller(
            "accountant",
            "Главный бухгалтер",
            FieldType.NAME,
            required=False,
            hint="Если его нет — оставьте пустым",
        ),
    ),
)

OFFER = BuiltinTemplate(
    slug="offer",
    title="Коммерческое предложение",
    kind="offer",
    description="Предложение клиенту: состав работ, сумма прописью, условия и срок действия.",
    blank="offer.docx",
    fields=(
        _subject("date", "Дата предложения", FieldType.DATE, carry_over=False),
        _number("Исходящий номер", required=False),
        _seller("name", "Название продавца", FieldType.TEXT),
        _seller("inn", "ИНН продавца", FieldType.INN, required=False),
        _seller("ogrn", "ОГРН продавца", FieldType.OGRN, required=False),
        _seller("address", "Адрес продавца", FieldType.ADDRESS, required=False),
        _seller("phone", "Телефон", FieldType.PHONE, required=False),
        _seller("email", "Почта", FieldType.EMAIL, required=False),
        _seller("site", "Сайт", FieldType.TEXT, required=False),
        _client(
            "recipient_position",
            "Должность получателя",
            FieldType.TEXT,
            required=False,
            hint="Кому: Генеральному директору",
        ),
        _client("name", "Название клиента", FieldType.TEXT),
        _client(
            "recipient",
            "Получатель",
            FieldType.TEXT,
            required=False,
            hint="Кому: Петрову Петру Петровичу",
        ),
        _client(
            "greeting",
            "Обращение",
            FieldType.TEXT,
            required=False,
            hint="Имя и отчество: Пётр Петрович",
        ),
        _subject(
            "subject",
            "Тема предложения",
            FieldType.TEXT,
            hint="Что предлагаете: оказание услуг по разработке сайта",
        ),
        _subject("scope", "Состав работ", FieldType.MULTILINE),
        *_QUANTITY,
        _subject("total", "Стоимость", FieldType.MONEY),
        _subject(
            "vat",
            "НДС",
            FieldType.TEXT,
            required=False,
            default="не облагается",
            hint="«не облагается» или «20% — 20 000,00 руб.»",
        ),
        _subject(
            "payment_terms",
            "Порядок оплаты",
            FieldType.TEXT,
            required=False,
            hint="Предоплата 50%, остаток — после сдачи работ",
        ),
        _subject("term", "Срок выполнения", FieldType.TEXT, required=False),
        _subject("delivery", "Доставка", FieldType.TEXT, required=False),
        _subject("warranty", "Гарантия", FieldType.TEXT, required=False),
        _subject(
            "valid_until",
            "Предложение действует до",
            FieldType.DATE,
            carry_over=False,
        ),
        _seller(
            "contact",
            "Контактное лицо",
            FieldType.TEXT,
            required=False,
            hint="Должность, фамилия, имя",
        ),
        _SIGNER_POSITION,
        _seller("director", "Подписант", FieldType.NAME, required=False, hint="Иванов И. И."),
    ),
)


def _requisites(side: str, name: str) -> tuple[FieldSpec, ...]:
    make = _seller if side == "seller" else _client
    return (
        make("kpp", f"КПП {name}", FieldType.KPP, required=False),
        make("ogrn", f"ОГРН {name}", FieldType.OGRN, required=False),
        make("address", f"Адрес {name}", FieldType.ADDRESS, required=False),
        make("bank", f"Банк {name}", FieldType.TEXT, required=False),
        make("bic", f"БИК {name}", FieldType.BIC, required=False),
        make("account", f"Расчётный счёт {name}", FieldType.ACCOUNT, required=False),
        make("corr_account", f"Корр. счёт {name}", FieldType.ACCOUNT, required=False),
        make("email", f"Почта {name}", FieldType.EMAIL, required=False),
    )


def _basis(side: str, name: str) -> FieldSpec:
    make = _seller if side == "seller" else _client
    return make(
        "basis",
        f"Основание полномочий {name}",
        FieldType.TEXT,
        required=False,
        default="Устава",
        hint="Действует на основании: Устава, доверенности № 5 от 01.09.2026",
    )


SERVICE_CONTRACT = BuiltinTemplate(
    slug="service-contract",
    title="Договор оказания услуг",
    kind="contract",
    description="Договор возмездного оказания услуг с заданием и формой акта.",
    blank="contract.docx",
    fields=(
        _number("Номер договора"),
        _subject("date", "Дата договора", FieldType.DATE, carry_over=False),
        _subject("city", "Город", FieldType.TEXT),
        _seller("name", "Название продавца", FieldType.TEXT),
        _seller("inn", "ИНН продавца", FieldType.INN),
        *_requisites("seller", "продавца"),
        _seller(
            "director",
            "Подписант продавца",
            FieldType.NAME,
            hint="В лице кого: генерального директора Иванова Ивана Ивановича",
        ),
        _basis("seller", "продавца"),
        _client("name", "Название клиента", FieldType.TEXT),
        _client("inn", "ИНН клиента", FieldType.INN),
        *_requisites("client", "клиента"),
        _client("director", "Подписант клиента", FieldType.NAME, required=False),
        _basis("client", "клиента"),
        _subject(
            "subject",
            "Предмет договора",
            FieldType.MULTILINE,
            hint="Оказать услуги… по разработке сайта",
        ),
        _subject(
            "service_place",
            "Место оказания услуг",
            FieldType.TEXT,
            required=False,
            default="удалённо",
            hint="Адрес или «удалённо»",
        ),
        _subject("total", "Стоимость услуг", FieldType.MONEY),
        _subject(
            "vat",
            "НДС",
            FieldType.TEXT,
            required=False,
            default="не облагается",
            hint="«не облагается» или «в том числе НДС 20% — 20 000,00 руб.»",
        ),
        _subject(
            "start",
            "Начало оказания услуг",
            FieldType.TEXT,
            required=False,
            default="со дня подписания Договора",
            hint="«со дня подписания Договора» или дата",
        ),
        _subject("end_date", "Услуги оказать до", FieldType.DATE, carry_over=False),
        _subject(
            "payment_days",
            "Срок оплаты после акта, рабочих дней",
            FieldType.INTEGER,
            required=False,
            default="5",
        ),
        _subject(
            "valid_until", "Договор действует до", FieldType.DATE, required=False, carry_over=False
        ),
        _subject(
            "requirements",
            "Требования к услугам и отчёту",
            FieldType.MULTILINE,
            required=False,
            default="в соответствии с Договором",
        ),
        _subject(
            "client_materials",
            "Что передаёт заказчик",
            FieldType.MULTILINE,
            required=False,
            default="по запросу Исполнителя",
            hint="Сведения, документы и доступы для работы",
        ),
        _subject(
            "expenses",
            "Возмещаемые расходы",
            FieldType.TEXT,
            required=False,
            default="не возмещаются",
        ),
    ),
)

BUILTIN_TEMPLATES: tuple[BuiltinTemplate, ...] = (INVOICE, OFFER, SERVICE_CONTRACT)
