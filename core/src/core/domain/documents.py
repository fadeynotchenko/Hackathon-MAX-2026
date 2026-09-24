"""Поля документа: типы, нормализация значений и проверка реквизитов.

Чистый домен без I/O: те же правила работают и для формы мини-аппа, и для
распознанной фотографии, и для значений, предложенных агентом. Реквизиты
проверяются контрольными суммами (ИНН, ОГРН, расчётный счёт) — ошибка в них
дороже любой опечатки в тексте: документ с чужим счётом уходит контрагенту.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from itertools import cycle


class FieldType(StrEnum):
    TEXT = "text"
    MULTILINE = "multiline"
    NAME = "name"
    ADDRESS = "address"
    EMAIL = "email"
    PHONE = "phone"
    MONEY = "money"
    DATE = "date"
    INTEGER = "integer"
    INN = "inn"
    KPP = "kpp"
    OGRN = "ogrn"
    BIC = "bic"
    ACCOUNT = "account"


class ValueSource(StrEnum):
    """Откуда взялось значение. Источник виден в предпросмотре и решает,
    нужно ли подтверждение человека: распознанное и предложенное агентом —
    черновик, ручной ввод и справочники — нет."""

    MANUAL = "manual"
    PROFILE = "profile"
    COUNTERPARTY = "counterparty"
    OCR = "ocr"
    AGENT = "agent"


UNCONFIRMED_SOURCES = frozenset({ValueSource.OCR, ValueSource.AGENT})


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    type: FieldType = FieldType.TEXT
    required: bool = True
    group: str = ""
    hint: str = ""
    max_length: int | None = None
    # Переносится ли значение в копию документа. Номер и даты у нового счёта
    # свои: скопированный номер ушёл бы контрагенту дублем.
    carry_over: bool = True


@dataclass(frozen=True)
class FieldValue:
    value: str
    source: ValueSource = ValueSource.MANUAL
    confidence: float | None = None
    confirmed: bool = True
    # Откуда прочитано: строка с фото или скана. Показывается рядом со значением,
    # чтобы человек сверял его с оригиналом, а не верил распознаванию на слово.
    fragment: str | None = None

    @property
    def needs_confirmation(self) -> bool:
        return self.source in UNCONFIRMED_SOURCES and not self.confirmed


@dataclass(frozen=True)
class FieldError:
    key: str
    code: str
    message: str


@dataclass(frozen=True)
class ValidatedFields:
    values: dict[str, FieldValue]
    errors: tuple[FieldError, ...] = ()
    missing: tuple[str, ...] = ()
    unconfirmed: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        """Готов к рендеру: ошибок нет, обязательные заполнены, распознанное подтверждено."""
        return not self.errors and not self.missing and not self.unconfirmed


_DIGITS = re.compile(r"\D+")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
_SPACES = re.compile(r"[\s ]+")


def _digits(raw: str) -> str:
    return _DIGITS.sub("", raw)


def _inn_valid(value: str) -> bool:
    def checksum(digits: str, weights: tuple[int, ...]) -> int:
        return sum(int(d) * w for d, w in zip(digits, weights, strict=False)) % 11 % 10

    if len(value) == 10:
        return checksum(value, (2, 4, 10, 3, 5, 9, 4, 6, 8)) == int(value[9])
    if len(value) == 12:
        first = checksum(value, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)) == int(value[10])
        second = checksum(value, (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)) == int(value[11])
        return first and second
    return False


def _ogrn_valid(value: str) -> bool:
    # ОГРН — 13 цифр с контролем по модулю 11, ОГРНИП — 15 по модулю 13.
    if len(value) == 13:
        return int(value[:12]) % 11 % 10 == int(value[12])
    if len(value) == 15:
        return int(value[:14]) % 13 % 10 == int(value[14])
    return False


def account_key_valid(account: str, bic: str) -> bool:
    """Ключ расчётного счёта считается вместе с БИК банка: без него 20 цифр
    проверить нечем, поэтому одиночный счёт домен принимает как есть."""
    account, bic = _digits(account), _digits(bic)
    if len(account) != 20 or len(bic) != 9:
        return False
    # Балансовые счета банка (начинаются на 0) ключуются по «0» и цифрам 5-6 БИК.
    prefix = "0" + bic[4:6] if account.startswith("0") else bic[6:9]
    weights = cycle((7, 1, 3))
    total = sum(int(d) * w for d, w in zip(prefix + account, weights, strict=False))
    return total % 10 == 0


def parse_money(raw: str) -> Decimal | None:
    """«120 000,50», «120000.50», «120 000 ₽» — одна и та же сумма."""
    cleaned = _SPACES.sub("", raw).replace("₽", "").replace("руб.", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if amount < 0 or amount.as_tuple().exponent < -2:
        return None
    return amount


def parse_date(raw: str) -> date | None:
    cleaned = raw.strip().replace("/", ".").replace("-", ".")
    parts = cleaned.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    if len(parts[0]) == 4:
        year, month, day = parts
    else:
        day, month, year = parts
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def format_money(amount: Decimal) -> str:
    whole, _, frac = f"{amount:.2f}".partition(".")
    groups = f"{int(whole):,}".replace(",", " ")
    return f"{groups},{frac}"


def normalize(spec: FieldSpec, raw: str) -> tuple[str, FieldError | None]:
    """Привести значение к каноническому виду хранения или объяснить, что не так."""
    value = raw.strip()
    if not value:
        return "", None

    def bad(code: str, message: str) -> tuple[str, FieldError]:
        return "", FieldError(spec.key, code, message)

    if spec.max_length is not None and len(value) > spec.max_length:
        return bad("field.too_long", f"«{spec.label}»: не длиннее {spec.max_length} символов")

    match spec.type:
        case FieldType.MONEY:
            amount = parse_money(value)
            if amount is None:
                return bad("field.money_invalid", f"«{spec.label}»: не похоже на сумму")
            return f"{amount:.2f}", None
        case FieldType.DATE:
            parsed = parse_date(value)
            if parsed is None:
                return bad("field.date_invalid", f"«{spec.label}»: дата в формате 31.12.2026")
            return parsed.isoformat(), None
        case FieldType.INTEGER:
            digits = _digits(value)
            if not digits or digits != value.lstrip("+"):
                return bad("field.integer_invalid", f"«{spec.label}»: только целое число")
            return digits, None
        case FieldType.EMAIL:
            if not _EMAIL.match(value):
                return bad("field.email_invalid", f"«{spec.label}»: не похоже на адрес почты")
            return value.lower(), None
        case FieldType.PHONE:
            digits = _digits(value)
            if len(digits) == 11 and digits[0] in {"7", "8"}:
                return "+7" + digits[1:], None
            if len(digits) == 10:
                return "+7" + digits, None
            return bad("field.phone_invalid", f"«{spec.label}»: телефон из 11 цифр")
        case FieldType.INN:
            digits = _digits(value)
            if not _inn_valid(digits):
                return bad("field.inn_invalid", f"«{spec.label}»: ИНН не проходит проверку")
            return digits, None
        case FieldType.KPP:
            digits = _digits(value)
            if len(digits) != 9:
                return bad("field.kpp_invalid", f"«{spec.label}»: КПП из 9 цифр")
            return digits, None
        case FieldType.OGRN:
            digits = _digits(value)
            if not _ogrn_valid(digits):
                return bad("field.ogrn_invalid", f"«{spec.label}»: ОГРН не проходит проверку")
            return digits, None
        case FieldType.BIC:
            digits = _digits(value)
            if len(digits) != 9:
                return bad("field.bic_invalid", f"«{spec.label}»: БИК из 9 цифр")
            return digits, None
        case FieldType.ACCOUNT:
            digits = _digits(value)
            if len(digits) != 20:
                return bad("field.account_invalid", f"«{spec.label}»: счёт из 20 цифр")
            return digits, None
        case _:
            return _SPACES.sub(" ", value) if spec.type is not FieldType.MULTILINE else value, None


def validate_fields(
    specs: tuple[FieldSpec, ...], incoming: Mapping[str, FieldValue]
) -> ValidatedFields:
    """Проверить весь набор значений разом: результат годится и для ответа API,
    и для решения «можно ли рендерить»."""
    known = {spec.key: spec for spec in specs}
    values: dict[str, FieldValue] = {}
    errors: list[FieldError] = []

    for key, incoming_value in incoming.items():
        spec = known.get(key)
        if spec is None:
            errors.append(FieldError(key, "field.unknown", f"Поле «{key}» не из этого шаблона"))
            continue
        normalized, error = normalize(spec, incoming_value.value)
        if error is not None:
            errors.append(error)
            continue
        if normalized:
            values[key] = replace(incoming_value, value=normalized)

    errors.extend(_cross_field_errors(known, values))
    missing = tuple(spec.key for spec in specs if spec.required and spec.key not in values)
    unconfirmed = tuple(key for key, value in values.items() if value.needs_confirmation)
    return ValidatedFields(values, tuple(errors), missing, unconfirmed)


def _cross_field_errors(
    known: Mapping[str, FieldSpec], values: Mapping[str, FieldValue]
) -> list[FieldError]:
    """Счёт и БИК проверяются только вместе, поэтому это не дело normalize."""
    errors: list[FieldError] = []
    bic_keys = [key for key, spec in known.items() if spec.type is FieldType.BIC]
    for key, spec in known.items():
        if spec.type is not FieldType.ACCOUNT or key not in values:
            continue
        bic_key = next((b for b in bic_keys if b in values), None)
        if bic_key is None:
            continue
        if not account_key_valid(values[key].value, values[bic_key].value):
            errors.append(
                FieldError(
                    key,
                    "field.account_key_invalid",
                    f"«{spec.label}»: счёт не сходится с БИК банка",
                )
            )
    return errors


def render_context(
    specs: tuple[FieldSpec, ...], values: Mapping[str, FieldValue]
) -> dict[str, str]:
    """Значения в том виде, в каком они попадают в текст документа."""
    out: dict[str, str] = {}
    for spec in specs:
        value = values.get(spec.key)
        if value is None:
            out[spec.key] = ""
            continue
        match spec.type:
            case FieldType.MONEY:
                amount = parse_money(value.value)
                out[spec.key] = format_money(amount) if amount is not None else value.value
            case FieldType.DATE:
                parsed = parse_date(value.value)
                out[spec.key] = parsed.strftime("%d.%m.%Y") if parsed else value.value
            case _:
                out[spec.key] = value.value
    return out


BLANK = "__________"
_MARKER = re.compile(r"{{\s*(\w+)\s*}}")


def fill_text_template(body: str, context: Mapping[str, str], *, blank: str = BLANK) -> str:
    """Подстановка ``{{key}}`` в тело шаблона.

    Пустое поле остаётся видимой прочерк-строкой, а не исчезает: документ с
    молча пропавшим реквизитом выглядит готовым и уходит контрагенту таким.
    Синтаксис маркера совпадает с DOCX-шаблонами, чтобы тело одного шаблона
    можно было перенести в файл без правки текста.
    """
    return _MARKER.sub(lambda m: context.get(m.group(1)) or blank, body)
