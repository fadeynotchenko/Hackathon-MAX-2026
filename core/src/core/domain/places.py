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
