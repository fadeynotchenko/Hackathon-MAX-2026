"""Сумма прописью и дата словами — так их пишут в счёте, договоре и КП.

«Всего к оплате: Сто двадцать тысяч рублей 00 копеек», «стоимость составляет
120 000 (сто двадцать тысяч) рублей 00 копеек», «от «28» сентября 2026 г.».
Чистые функции без I/O: их зовёт подстановка значений в шаблон.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

_UNITS_MALE = ("", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_UNITS_FEMALE = ("", "одна", "две", *_UNITS_MALE[3:])
_TEENS = (
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
_TENS = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
_HUNDREDS = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)
# Разряды: формы «один / два–четыре / пять» и род числительного перед ними.
_SCALES = (
    (("тысяча", "тысячи", "тысяч"), True),
    (("миллион", "миллиона", "миллионов"), False),
    (("миллиард", "миллиарда", "миллиардов"), False),
)
_MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


MONTH_NUMBERS = {name: number for number, name in enumerate(_MONTHS_GENITIVE, 1)}


def plural(number: int, forms: tuple[str, str, str]) -> str:
    """«1 рубль», «2 рубля», «5 рублей», «11 рублей», «21 рубль»."""
    tail = number % 100
    if 11 <= tail <= 14:
        return forms[2]
    last = number % 10
    if last == 1:
        return forms[0]
    if 2 <= last <= 4:
        return forms[1]
    return forms[2]


def _triad(number: int, *, female: bool) -> list[str]:
    hundreds, rest = divmod(number, 100)
    words = [_HUNDREDS[hundreds]]
    if 10 <= rest <= 19:
        words.append(_TEENS[rest - 10])
    else:
        tens, units = divmod(rest, 10)
        words += [_TENS[tens], (_UNITS_FEMALE if female else _UNITS_MALE)[units]]
    return [word for word in words if word]


def number_words(number: int, *, female: bool = False) -> str:
    """Целое словами: 120000 → «сто двадцать тысяч». ``female`` — для слов
    женского рода после числа: «одна копейка», «две тысячи»."""
    if number == 0:
        return "ноль"
    words: list[str] = []
    rest = number
    groups: list[int] = []
    while rest:
        rest, group = divmod(rest, 1000)
        groups.append(group)
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if group == 0:
            continue
        if index == 0:
            words += _triad(group, female=female)
            continue
        forms, scale_female = _SCALES[index - 1]
        words += [*_triad(group, female=scale_female), plural(group, forms)]
    return " ".join(words)


def rubles_kopecks(amount: Decimal) -> tuple[int, int]:
    kopecks = int((amount * 100).to_integral_value())
    return divmod(kopecks, 100)


def money_words(amount: Decimal) -> str:
    """«Сто двадцать тысяч рублей 00 копеек» — строка «сумма прописью» счёта."""
    rubles, kopecks = rubles_kopecks(amount)
    text = (
        f"{number_words(rubles)} {plural(rubles, ('рубль', 'рубля', 'рублей'))} "
        f"{kopecks:02d} {plural(kopecks, ('копейка', 'копейки', 'копеек'))}"
    )
    return text[0].upper() + text[1:]


def month_genitive(day: date) -> str:
    return _MONTHS_GENITIVE[day.month - 1]


def date_long(day: date) -> str:
    """«28» сентября 2026 г. — дата в шапке договора и в сроках."""
    return f"«{day.day:02d}» {month_genitive(day)} {day.year} г."
