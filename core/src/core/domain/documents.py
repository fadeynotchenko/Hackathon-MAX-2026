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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from itertools import cycle

from core.domain.words import (
    MONTH_NUMBERS,
    date_long,
    money_words,
    month_genitive,
    number_words,
    rubles_kopecks,
)


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
    # Поставлено системой при создании (дата счёта — сегодня, «Без НДС» в счёте):
    # не угадано моделью, видно в форме и правится как обычное значение.
    DEFAULT = "default"
    # Стояло в файле, по которому сделан документ: человек прислал свой документ
    # и меняет в нём данные. Текст взят из файла буквально, подтверждать нечего.
    FILE = "file"


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
    # Пустое поле при создании документа получает сегодняшнюю дату по Москве.
    today_by_default: bool = False
    # Значение нового документа, пока человек не ввёл своё: «Без НДС», «Устава».
    default: str = ""


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

    @property
    def renderable(self) -> bool:
        """Можно собрать файл: ошибок нет, распознанное подтверждено. Пустое
        обязательное поле сборку не держит — человек вправе оставить его и
        вписать от руки; в файле оно останется линией, а статус — «черновик»."""
        return not self.errors and not self.unconfirmed


# Только ASCII-цифры: «٧٧٠٧…» (арабские) \d тоже считает цифрами, и такой ИНН
# проходил проверку, но не совпадал с тем же ИНН, набранным обычными цифрами.
_DIGITS = re.compile(r"[^0-9]+")
_INTEGER = re.compile(r"^\+?([0-9][0-9 ]*?)\s*[а-яёa-z.]*$", re.IGNORECASE)
_KPP = re.compile(r"^[0-9]{4}[0-9A-Z]{2}[0-9]{3}$")
_NOT_KPP = re.compile(r"[^0-9A-Z]")
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


def account_key_valid(account: str, bic: str, *, correspondent: bool = False) -> bool:
    """Ключ расчётного счёта считается вместе с БИК банка: без него 20 цифр
    проверить нечем, поэтому одиночный счёт домен принимает как есть."""
    account, bic = _digits(account), _digits(bic)
    if len(account) != 20 or len(bic) != 9:
        return False
    # Корреспондентский счёт и балансовые счета банка (начинаются на 0) ключуются
    # по «0» и цифрам 5-6 БИК, расчётный — по последним трём цифрам БИК.
    prefix = "0" + bic[4:6] if correspondent or account.startswith("0") else bic[6:9]
    weights = cycle((7, 1, 3))
    total = sum(int(d) * w for d, w in zip(prefix + account, weights, strict=False))
    return total % 10 == 0


# Потолок суммы: триллион с копейками. Дальше — опечатка, а «1e999999» без
# потолка превращался бы в строку из миллиона цифр в документе и базе.
MAX_MONEY = Decimal("999999999999.99")


# «150 000 рублей», «150 тыс. руб.», «1,5 млн» — так суммы пишут в сообщениях.
_CURRENCY = re.compile(r"(₽|руб(лей|ля|ль|\.)?|р\.?)$")
_THOUSANDS = re.compile(r"(тыс(яч[аи]?|\.)?|т\.?|к)$")
_MILLIONS = re.compile(r"(млн\.?|миллион(а|ов)?)$")


def parse_money(raw: str) -> Decimal | None:
    """«120 000,50», «120000.50», «120 000 ₽» — одна и та же сумма."""
    cleaned = _CURRENCY.sub("", _SPACES.sub("", raw).lower())
    factor = 1
    for unit, multiplier in ((_THOUSANDS, 1000), (_MILLIONS, 1_000_000)):
        if unit.search(cleaned):
            cleaned, factor = unit.sub("", cleaned), multiplier
            break
    cleaned = cleaned.replace(",", ".")
    if not cleaned:
        return None
    try:
        amount = Decimal(cleaned) * factor
    except InvalidOperation:
        return None
    # «NaN» и «Infinity» Decimal принимает, но сравнивать их нельзя: не сумма.
    if not amount.is_finite() or amount < 0 or amount > MAX_MONEY:
        return None
    # «1,555 тыс.» — это 1555 рублей ровно, а не 1555,000 с лишними знаками.
    if (amount.normalize() if factor > 1 else amount).as_tuple().exponent < -2:
        return None
    # «-0» — тот же ноль, без минуса в документе.
    return abs(amount)


# «31.12.2026 г.», «31.12.2026г» — так дату пишут в документах и сообщениях.
_YEAR_SUFFIX = re.compile(r"\s*(г\.?|года)$", re.IGNORECASE)
MIN_YEAR, MAX_YEAR = 1900, 2100


# «28» сентября 2026 г., 28 сентября 2026 — так дату пишут в шапке договора.
_WORDY_DATE = re.compile(r'^[«"]?(\d{1,2})[»"]?\s+([а-яё]+)\s+(\d{4})$', re.IGNORECASE)


def parse_date(raw: str) -> date | None:
    wordy = _WORDY_DATE.match(_YEAR_SUFFIX.sub("", raw.strip()))
    if wordy is not None:
        month = MONTH_NUMBERS.get(wordy.group(2).lower())
        if month is None or not MIN_YEAR <= int(wordy.group(3)) <= MAX_YEAR:
            return None
        try:
            return date(int(wordy.group(3)), month, int(wordy.group(1)))
        except ValueError:
            return None
    cleaned = _YEAR_SUFFIX.sub("", raw.strip()).replace("/", ".").replace("-", ".")
    parts = cleaned.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    if len(parts[0]) == 4:
        year, month, day = parts
    else:
        day, month, year = parts
    # «01.10.26» — это 2026 год, а не 26-й нашей эры.
    full_year = int(year) + 2000 if len(year) == 2 else int(year)
    if not MIN_YEAR <= full_year <= MAX_YEAR:
        return None
    try:
        return date(full_year, int(month), int(day))
    except ValueError:
        return None


def format_money(amount: Decimal) -> str:
    whole, _, frac = f"{amount:.2f}".partition(".")
    groups = f"{int(whole):,}".replace(",", " ")
    return f"{groups},{frac}"


# Невидимые символы (пробел нулевой ширины, BOM) превращали пустое поле в
# «заполненное»; управляющие не принимает PostgreSQL (NUL) и сборка DOCX (XML).
_INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff\u00ad]")
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Предел длины по типу, если шаблон не задал свой: реквизит или адрес длиннее —
# вставленный по ошибке текст, а не значение.
DEFAULT_MAX_LENGTH = {FieldType.MULTILINE: 5000, FieldType.EMAIL: 254}
TEXT_MAX_LENGTH = 1000
INTEGER_MAX_DIGITS = 9


def normalize(spec: FieldSpec, raw: str) -> tuple[str, FieldError | None]:
    """Привести значение к каноническому виду хранения или объяснить, что не так."""
    value = _INVISIBLE.sub("", raw).strip()
    if not value:
        return "", None

    def bad(code: str, message: str) -> tuple[str, FieldError]:
        return "", FieldError(spec.key, code, message)

    if _CONTROL.search(value):
        return bad("field.control_chars", f"«{spec.label}»: в значении есть служебные символы")
    limit = spec.max_length or DEFAULT_MAX_LENGTH.get(spec.type, TEXT_MAX_LENGTH)
    if len(value) > limit:
        return bad("field.too_long", f"«{spec.label}»: не длиннее {limit} символов")

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
            # «10 дней» в поле «Срок, дней» — это 10: единица уже в названии поля.
            match = _INTEGER.match(value)
            if match is None or len(_digits(match.group(1))) > INTEGER_MAX_DIGITS:
                return bad("field.integer_invalid", f"«{spec.label}»: только целое число")
            return str(int(_digits(match.group(1)))), None
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
            # В 5–6 знаках КПП бывают латинские буквы (причина постановки на учёт).
            kpp = _NOT_KPP.sub("", value.upper())
            if not _KPP.match(kpp):
                return bad("field.kpp_invalid", f"«{spec.label}»: КПП из 9 цифр")
            return kpp, None
        case FieldType.OGRN:
            digits = _digits(value)
            if not _ogrn_valid(digits):
                return bad("field.ogrn_invalid", f"«{spec.label}»: ОГРН не проходит проверку")
            return digits, None
        case FieldType.BIC:
            digits = _digits(value)
            if len(digits) != 9:
                return bad("field.bic_invalid", f"«{spec.label}»: БИК из 9 цифр")
            # Первые две цифры — код страны: у российских банков всегда 04.
            if not digits.startswith("04"):
                return bad("field.bic_invalid", f"«{spec.label}»: БИК банка начинается с 04")
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
            errors.append(FieldError(key, "field.unknown", f"Неизвестное поле «{key}»"))
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


# Корреспондентский счёт банка: ``seller_corr_account``. Ключуется иначе, чем расчётный.
CORR_ACCOUNT_SUFFIX = "corr_account"
_BANK_SUFFIX = re.compile(r"_?(?:corr_account|account|bic)$")


def _cross_field_errors(
    known: Mapping[str, FieldSpec], values: Mapping[str, FieldValue]
) -> list[FieldError]:
    """Счёт и БИК проверяются только вместе, поэтому это не дело normalize."""
    errors: list[FieldError] = []
    bic_keys = [key for key, spec in known.items() if spec.type is FieldType.BIC]
    for key, spec in known.items():
        if spec.type is not FieldType.ACCOUNT or key not in values:
            continue
        bic_key = _bic_for(key, bic_keys)
        if bic_key is None or bic_key not in values:
            continue
        correspondent = key.endswith(CORR_ACCOUNT_SUFFIX)
        if not account_key_valid(
            values[key].value, values[bic_key].value, correspondent=correspondent
        ):
            errors.append(
                FieldError(
                    key,
                    "field.account_key_invalid",
                    f"«{spec.label}»: счёт не сходится с БИК банка",
                )
            )
    return errors


def _side(key: str) -> str:
    """Сторона реквизита: ``seller`` у ``seller_account``, ``seller_corr_account`` и ``seller_bic``."""
    side, found = _BANK_SUFFIX.subn("", key)
    return side if found else key.rpartition("_")[0]


def _bic_for(account_key: str, bic_keys: list[str]) -> str | None:
    """БИК той же стороны: ``seller_account`` сверяется с ``seller_bic``, а не с
    первым попавшимся БИК шаблона — иначе счёт клиента проверялся бы банком продавца."""
    side = _side(account_key)
    same_side = [key for key in bic_keys if _side(key) == side]
    if same_side:
        return same_side[0]
    return bic_keys[0] if len(bic_keys) == 1 else None


def format_phone(value: str) -> str:
    """«+79001234567» → «+7 900 123-45-67»: так номер читают в документе."""
    digits = _digits(value)
    if len(digits) != 11 or not value.startswith("+7"):
        return value
    return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"


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
            case FieldType.PHONE:
                out[spec.key] = format_phone(value.value)
            case _:
                out[spec.key] = value.value
    return out


BLANK = "__________"
# Маркер поля: {{total}} — значение как есть, {{total|words}} — вариант записи
# того же значения (сумма прописью, дата словами). Варианты считает fill_context.
MARKER = re.compile(r"{{\s*(\w+)(?:\s*\|\s*([\w:]+))?\s*}}")


def marker_name(match: re.Match[str]) -> str:
    """Ключ значения в контексте подстановки: ``total`` или ``total|words``."""
    key, variant = match.group(1), match.group(2)
    return f"{key}|{variant}" if variant else key


def template_markers(body: str) -> list[str]:
    """Ключи полей в теле шаблона по порядку появления, без повторов. Поле из
    аргумента варианта (``quantity`` в ``{{total|per:quantity}}``) — тоже в тексте."""
    keys: list[str] = []
    for match in MARKER.finditer(body):
        keys.append(match.group(1))
        variant = match.group(2) or ""
        if ":" in variant:
            keys.append(variant.split(":", 1)[1])
    return list(dict.fromkeys(keys))


def _money_variants(key: str, amount: Decimal) -> dict[str, str]:
    rubles, kopecks = rubles_kopecks(amount)
    return {
        f"{key}|words": money_words(amount),
        f"{key}|rub": format_money(Decimal(rubles)).partition(",")[0],
        f"{key}|rub_words": number_words(rubles),
        f"{key}|kop": f"{kopecks:02d}",
    }


def _date_variants(key: str, day: date) -> dict[str, str]:
    return {
        f"{key}|long": date_long(day),
        f"{key}|text": f"{day.day:02d} {month_genitive(day)} {day.year}",
        f"{key}|day": f"{day.day:02d}",
        f"{key}|month": month_genitive(day),
        f"{key}|year": str(day.year),
        f"{key}|yy": f"{day.year % 100:02d}",
    }


def fill_context(specs: tuple[FieldSpec, ...], values: Mapping[str, FieldValue]) -> dict[str, str]:
    """Всё, что подставляется в шаблон: значения полей и варианты их записи.

    Сумма — ещё и прописью, рублями и копейками отдельно («120 000 (сто двадцать
    тысяч) рублей 00 копеек»), ценой за единицу и НДС в том числе, если в шаблоне
    есть целое число (``{{total|per:quantity}}``, ``{{total|vat:vat_rate}}``);
    дата — словами и по частям для бланков вида «____» ________ 20__ г.»."""
    out = render_context(specs, values)
    numbers = {
        spec.key: int(values[spec.key].value)
        for spec in specs
        if spec.type is FieldType.INTEGER
        and spec.key in values
        and values[spec.key].value.isdigit()
    }
    for spec in specs:
        value = values.get(spec.key)
        if value is None:
            continue
        if spec.type is FieldType.MONEY and (amount := parse_money(value.value)) is not None:
            out |= _money_variants(spec.key, amount)
            for number_key, number in numbers.items():
                if number > 0:
                    share = (amount / number).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    out[f"{spec.key}|per:{number_key}"] = format_money(share)
                # НДС в том числе по ставке из целого поля: 120 000 при 20% — 20 000,00.
                vat = (amount * number / (100 + number)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                out[f"{spec.key}|vat:{number_key}"] = format_money(vat)
        elif spec.type is FieldType.DATE and (day := parse_date(value.value)) is not None:
            out |= _date_variants(spec.key, day)
    return out


def fill_text_template(body: str, context: Mapping[str, str], *, blank: str = BLANK) -> str:
    """Подстановка ``{{key}}`` и ``{{key|вариант}}`` в тело шаблона.

    Пустое поле остаётся видимой прочерк-строкой, а не исчезает: документ с
    молча пропавшим реквизитом выглядит готовым и уходит контрагенту таким.
    Синтаксис маркера совпадает с DOCX-шаблонами, чтобы тело одного шаблона
    можно было перенести в файл без правки текста.
    """
    return MARKER.sub(lambda m: context.get(marker_name(m)) or blank, body)
