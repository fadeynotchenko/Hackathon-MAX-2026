"""Места для данных в файле-образце: где в тексте стоит значение поля.

Свой шаблон можно сделать из готового документа — «рыбы»: в нём уже написаны
клиент, сумма, даты. Место — это такой фрагмент (``text``), который в новом
документе заменится значением поля. Если фрагмент сам по себе неоднозначен —
пустая линия «______» или короткое число, — его уточняет текст перед ним в той
же строке (``before``): «Заказчик: ______».

Одни и те же правила работают для строки текста и для абзаца DOCX: сборщик
файла ищет места в тексте абзаца этими функциями и меняет только найденные
отрезки, не трогая оформление вокруг.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

# Метка, которую человек сам написал в файле: {{Название клиента}}.
LABEL_MARKER = re.compile(r"{{\s*([^{}\n]+?)\s*}}")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Place:
    text: str
    before: str = ""


def label_of(marker_text: str) -> str:
    """«{{ Название   клиента }}» → «Название клиента»."""
    match = LABEL_MARKER.fullmatch(marker_text)
    return _SPACES.sub(" ", match.group(1)).strip() if match else ""


def place_spans(text: str, places: Sequence[tuple[str, Place]]) -> list[tuple[int, int, str]]:
    """Отрезки строки, которые занимают места полей: ``(начало, конец, ключ)``.

    Длинные места ищутся первыми: «ООО «Альфа Плюс»» не должно достаться полю,
    которому принадлежит «Альфа». Отрезки не пересекаются; ``before`` в отрезок
    не входит — он остаётся текстом документа."""
    taken: list[tuple[int, int, str]] = []
    ordered = sorted(places, key=lambda item: -len(item[1].before + item[1].text))
    for key, place in ordered:
        if not place.text:
            continue
        needle = place.before + place.text
        start = text.find(needle)
        while start != -1:
            begin, end = start + len(place.before), start + len(needle)
            if all(end <= s or begin >= e for s, e, _ in taken):
                taken.append((begin, end, key))
            start = text.find(needle, start + len(needle))
    return sorted(taken)


def apply_places(text: str, places: Sequence[tuple[str, Place]]) -> str:
    """Строка образца → строка шаблона: места становятся маркерами ``{{key}}``."""
    for begin, end, key in reversed(place_spans(text, places)):
        text = text[:begin] + "{{" + key + "}}" + text[end:]
    return text


def found(lines: Sequence[str], place: Place) -> bool:
    return any(place.before + place.text in line for line in lines)


# Типографика, которую модель переписывает по-своему: неразрывный пробел и
# табуляция — пробелом, «ёлочки» и „лапки“ — прямыми кавычками, тире — дефисом.
_TYPOGRAPHY = str.maketrans(
    {"«": '"', "»": '"', "„": '"', "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", "ё": "е"}
)


def _loose(text: str) -> tuple[str, list[int]]:
    """Строка без различий типографики и позиция каждого её символа в исходной."""
    out: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            if out and out[-1] == " ":
                continue
            char = " "
        out.append(char.translate(_TYPOGRAPHY))
        origin.append(index)
    return "".join(out), origin


def anchor(lines: Sequence[str], fragment: str) -> str | None:
    """Фрагмент так, как он написан в файле.

    Модель возвращает «символ в символ» не всегда: «ООО "Альфа"» вместо
    «ООО «Альфа»», обычный пробел вместо неразрывного из DOCX. Такое место
    не находилось точным поиском и молча пропадало из шаблона. Здесь оно
    ищется без различий типографики, а возвращается исходный отрезок строки —
    сборщик файла и дальше ищет точное совпадение."""
    if not fragment.strip():
        return None
    if any(fragment in line for line in lines):
        return fragment
    needle, _ = _loose(fragment.strip())
    for line in lines:
        loose, origin = _loose(line)
        start = loose.find(needle)
        if start != -1:
            return line[origin[start] : origin[start + len(needle) - 1] + 1]
    return None
