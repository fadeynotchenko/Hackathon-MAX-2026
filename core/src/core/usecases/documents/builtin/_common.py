"""Общее для стандартных бланков: шаблон, разделы формы и поля, которые повторяются."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

from core.domain.documents import FieldSpec, FieldType

SELLER = "Продавец"
CLIENT = "Клиент"
SUBJECT = "Предмет"
# Подпись стороны в названии поля: «ИНН продавца», как в каталоге полей своего шаблона.
SIDE_NAME = {"seller": "продавца", "client": "клиента"}


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


def seller(key: str, label: str, field_type: FieldType, **extra: object) -> FieldSpec:
    return FieldSpec(f"seller_{key}", label, field_type, group=SELLER, **extra)  # type: ignore[arg-type]


def client(key: str, label: str, field_type: FieldType, **extra: object) -> FieldSpec:
    return FieldSpec(f"client_{key}", label, field_type, group=CLIENT, **extra)  # type: ignore[arg-type]


def subject(key: str, label: str, field_type: FieldType, **extra: object) -> FieldSpec:
    return FieldSpec(key, label, field_type, group=SUBJECT, **extra)  # type: ignore[arg-type]


def side(name: str, key: str, label: str, field_type: FieldType, **extra: object) -> FieldSpec:
    make = seller if name == "seller" else client
    return make(key, label, field_type, **extra)


def number(label: str, *, required: bool = True) -> FieldSpec:
    return subject(
        "number", label, FieldType.TEXT, required=required, max_length=32, carry_over=False
    )


def date(label: str, *, today: bool = True) -> FieldSpec:
    return subject("date", label, FieldType.DATE, carry_over=False, today_by_default=today)


# Реквизиты стороны, которые бланк печатает, но без которых документ не
# ломается: у ИП нет КПП, у клиента не всегда известен банк.
_OPTIONAL_REQUISITES = {
    "kpp": ("КПП", FieldType.KPP),
    "ogrn": ("ОГРН", FieldType.OGRN),
    "address": ("Адрес", FieldType.ADDRESS),
    "bank": ("Банк", FieldType.TEXT),
    "bic": ("БИК", FieldType.BIC),
    "account": ("Расчётный счёт", FieldType.ACCOUNT),
    "corr_account": ("Корр. счёт", FieldType.ACCOUNT),
    "phone": ("Телефон", FieldType.PHONE),
    "email": ("Почта", FieldType.EMAIL),
}


def requisites(name: str, *keys: str) -> tuple[FieldSpec, ...]:
    """Необязательные реквизиты стороны в порядке ``keys``."""
    return tuple(
        side(
            name,
            key,
            f"{_OPTIONAL_REQUISITES[key][0]} {SIDE_NAME[name]}",
            _OPTIONAL_REQUISITES[key][1],
            required=False,
        )
        for key in keys
    )


def party(name: str, *, inn: bool = True) -> tuple[FieldSpec, ...]:
    """Название и ИНН стороны — без них сторона в документе не названа."""
    fields = [side(name, "name", f"Название {SIDE_NAME[name]}", FieldType.TEXT)]
    if inn:
        fields.append(side(name, "inn", f"ИНН {SIDE_NAME[name]}", FieldType.INN))
    return tuple(fields)


def director(name: str, *, required: bool = False) -> FieldSpec:
    return side(
        name,
        "director",
        f"Подписант {SIDE_NAME[name]}",
        FieldType.NAME,
        required=required,
        # В бланке имя стоит в именительном падеже («от имени которого действует
        # Иванов Иван Иванович»): то же значение идёт в подпись и приходит из
        # карточки организации без склонения.
        hint="Фамилия, имя, отчество: Иванов Иван Иванович",
    )


def basis(name: str) -> FieldSpec:
    return side(
        name,
        "basis",
        f"Основание полномочий {SIDE_NAME[name]}",
        FieldType.TEXT,
        required=False,
        default="Устава",
        hint="Действует на основании: Устава, доверенности № 5 от 01.09.2026",
    )


def quantity(*, unit: str = "усл.") -> tuple[FieldSpec, ...]:
    """Одна строка позиций на весь предмет: количество и единица — для цены за единицу."""
    return (
        subject("quantity", "Количество", FieldType.INTEGER, required=False, default="1"),
        subject(
            "unit", "Единица", FieldType.TEXT, required=False, default=unit, hint="усл., шт., ч"
        ),
    )


def items(*, unit: str = "усл.") -> FieldSpec:
    """Позиции таблицы: строка бланка повторяется на каждую, итог, НДС и сумма
    прописью считаются из них — отдельного поля «Сумма» у такого шаблона нет."""
    return subject(
        "items",
        "Позиции",
        FieldType.ITEMS,
        hint=f"Наименование, количество, единица ({unit}) и цена за единицу",
    )


def signer_position() -> FieldSpec:
    return seller(
        "position",
        "Должность подписанта",
        FieldType.TEXT,
        required=False,
        hint="Генеральный директор, Индивидуальный предприниматель",
    )


def vat_rate() -> FieldSpec:
    return subject(
        "vat_rate",
        "Ставка НДС, %",
        FieldType.INTEGER,
        required=False,
        default="22",
        hint="0 — без НДС; сумма НДС в том числе считается сама",
    )


def total(label: str = "Стоимость услуг") -> FieldSpec:
    return subject("total", label, FieldType.MONEY)


def scope(*, default: str = "", required: bool = False) -> FieldSpec:
    return subject(
        "scope",
        "Состав услуг",
        FieldType.MULTILINE,
        required=required,
        default=default,
        hint="Что входит в услуги — по строке на пункт",
    )
