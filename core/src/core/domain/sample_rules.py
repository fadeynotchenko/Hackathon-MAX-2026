"""Места для данных в «рыбе» без помощника — по разметке и виду значений.

Когда модели нет (ключ не задан, провайдер не ответил или ничего не нашёл),
места всё равно видны по самому тексту:

- линейка «______» с подписью перед ней: «ИНН / КПП: ______», «в лице ______»;
- дата-бланк ««____» ________ 20__ г.»;
- заполненные реквизиты: «ИНН 7707083893», «БИК 044525225», «р/с 40702…»;
- даты «28.09.2026» и «28 сентября 2026 г.», номер «№ 17» в заголовке;
- строка «Подпись: значение» — «Покупатель: ООО «Альфа»».

Правила только предлагают места: человек их проверяет, как и найденные
помощником. Одинаковое значение в разных местах — одно поле, разные значения
с одной подписью — разные поля («ИНН», «ИНН (2)»).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from core.domain.documents import FieldType
from core.domain.places import Place, place_spans

# Сколько текста перед линейкой уточняет её место: подпись, а не весь абзац.
BEFORE_MAX = 40
LABEL_WORDS = 3
LABEL_MAX = 60
_MONTHS = "января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря"
_DATE_BLANK = re.compile(r"«\s*_+\s*»\s*_+\s*(?:20)?_+\s*(?:г\.?)?")
_BLANK = re.compile(r"_{3,}")
_REQUISITE = re.compile(
    r"(?P<label>ИНН|КПП|БИК|ОГРНИП|ОГРН|[Рр]/с|[Кк]/с|Сч\.\s*№|[Рр]асч[её]тный сч[её]т"
    r"|[Кк]орр?\.?\s*сч[её]т)[\s:№]*(?P<value>\d{9,20})(?!\d)"
)
_DATE = re.compile(
    rf"(?<!\d)(?:\d{{2}}\.\d{{2}}\.\d{{4}}|[«\"]?\d{{1,2}}[»\"]?\s+(?:{_MONTHS})\s+\d{{4}}\s*г?\.?)(?!\d)"
)
_NUMBER = re.compile(r"№\s*(?P<value>\d[\w/-]{0,19})")
_LABELED = re.compile(r"^(?P<label>[А-ЯЁA-Z][^:_«»]{1,38}?):\s+(?P<value>[^_\s].{1,198})$")
_WORD = re.compile(r"[\w/.№-]+")
# Тип по подписи. Реквизит — только если подпись им и исчерпывается: у
# «ИНН / КПП: ______» значение двойное, проверка ИНН его бы отвергла.
_REQUISITE_TYPES = {
    "ИНН": FieldType.INN,
    "КПП": FieldType.KPP,
    "БИК": FieldType.BIC,
    "ОГРН": FieldType.OGRN,
    "ОГРНИП": FieldType.OGRN,
    "Р/с": FieldType.ACCOUNT,
    "К/с": FieldType.ACCOUNT,
    "Расчётный счёт": FieldType.ACCOUNT,
}
_TYPES = (
    (re.compile(r"e-?mail|почта", re.IGNORECASE), FieldType.EMAIL),
    (re.compile(r"(?<![а-яё])тел(?:\.|ефон|$)", re.IGNORECASE), FieldType.PHONE),
    (re.compile(r"^адрес", re.IGNORECASE), FieldType.ADDRESS),
    (re.compile(r"^(?:сумма|стоимость|цена|итого)(?:\s|:|$)", re.IGNORECASE), FieldType.MONEY),
    (re.compile(r"^(?:в лице|ФИО|фамилия)", re.IGNORECASE), FieldType.NAME),
)
_LETTERS = re.compile(r"[А-Яа-яЁёA-Za-z]{2,}")
_SPECIAL_LABELS = {"г.": "Город", "г": "Город", "№": "Номер", "от": "Дата"}


@dataclass
class RuleField:
    label: str
    type: FieldType
    places: list[Place] = field(default_factory=list)
    # Ключ каталога: номер и дата документа из заголовка; остальное — своё поле.
    key: str = ""
    # Значение в файле: у линейки его нет.
    value: str = ""


def _label(segment: str) -> str:
    """Подпись линейки — последние слова перед ней: «ИНН / КПП: » → «ИНН / КПП»,
    «…оказать услуги » → «Оказать услуги»."""
    text = re.split(r"[,;(]|\.\s", segment.rstrip())[-1]
    text = text.strip(" :—–-\t«»\"'")
    if text in _SPECIAL_LABELS:
        return _SPECIAL_LABELS[text]
    words = _WORD.findall(text)
    if not words:
        return ""
    label = " ".join(words[-LABEL_WORDS:]).strip(" .")
    if label.endswith("№"):
        label = "Номер"
    label = label[:LABEL_MAX]
    # Подпись — слова, а не «/» или союз «и» перед линейкой.
    if not _LETTERS.search(label) or any(char.isdigit() for char in label):
        return ""
    return label[:1].upper() + label[1:]


def _type(label: str) -> FieldType:
    if label in _REQUISITE_TYPES:
        return _REQUISITE_TYPES[label]
    for pattern, field_type in _TYPES:
        if pattern.search(label):
            return field_type
    return FieldType.TEXT


class _Collector:
    def __init__(self) -> None:
        self.fields: list[RuleField] = []

    def add(
        self,
        label: str,
        field_type: FieldType,
        place: Place,
        *,
        value: str = "",
        key: str = "",
    ) -> None:
        if not label:
            return
        # То же значение (или та же линейка) — то же поле; иначе новое с номером.
        for existing in self.fields:
            same = existing.value == value if value else place in existing.places
            if same and existing.label.split(" (")[0] == label:
                if place not in existing.places:
                    existing.places.append(place)
                return
        taken = {existing.label for existing in self.fields}
        name, n = label, 1
        while name in taken:
            n += 1
            name = f"{label} ({n})"
        self.fields.append(RuleField(name, field_type, [place], key=key, value=value))


def _blank_places(line: str, collector: _Collector) -> None:
    spans = [(m.start(), m.end(), True) for m in _DATE_BLANK.finditer(line)]
    spans += [
        (m.start(), m.end(), False)
        for m in _BLANK.finditer(line)
        if not any(s <= m.start() < e for s, e, _ in spans)
    ]
    previous = 0
    for start, end, is_date in sorted(spans):
        segment = line[previous:start]
        previous = end
        before = segment[-BEFORE_MAX:]
        if not before.strip():
            # Линейка без подписи рядом — чья она, не понять; дата-бланк понятен сам.
            if not is_date:
                continue
            before = segment[-BEFORE_MAX:]
        label = "Дата" if is_date and not _label(segment) else _label(segment)
        field_type = FieldType.DATE if is_date else _type(label)
        if is_date and label != "Дата":
            label = f"Дата: {label.lower()}"
        collector.add(label, field_type, Place(line[start:end], before))


def _value_places(line: str, index: int, collector: _Collector) -> None:
    for match in _REQUISITE.finditer(line):
        label = match.group("label")
        label = {"р/с": "Р/с", "к/с": "К/с"}.get(label, label)
        if label.lower().startswith(("сч", "расч")):
            label = "Расчётный счёт"
        elif label.lower().startswith("корр"):
            label = "К/с"
        field_type = _type(label)
        value = match.group("value")
        # Уточнение — только сама подпись («ИНН »): длинное место вокруг
        # («Поставщик: ООО…, ИНН …») должно перевесить, оно и заменяется.
        before = line[match.start("label") : match.start("value")]
        collector.add(label, field_type, Place(value, before), value=value)
    for match in _DATE.finditer(line):
        value = match.group(0).strip()
        key = "date" if not any(f.key == "date" for f in collector.fields) else ""
        collector.add("Дата", FieldType.DATE, Place(value), value=value, key=key)
    if index < 5:
        number = _NUMBER.search(line)
        if number is not None and not any(f.key == "number" for f in collector.fields):
            value = number.group("value")
            before = line[number.start() : number.start("value")]
            collector.add("Номер", FieldType.TEXT, Place(value, before), value=value, key="number")
    labeled = _LABELED.match(line.strip())
    if labeled is not None:
        label = labeled.group("label").strip()
        value = labeled.group("value").strip()
        if (
            len(_WORD.findall(label)) <= 4
            and not any(char.isdigit() for char in label)
            and "__" not in value
            and not _REQUISITE.fullmatch(value)
        ):
            collector.add(label, _type(label), Place(value, f"{label}: "), value=value)


def rule_fields(lines: Sequence[str], *, limit: int = 50) -> list[RuleField]:
    """Места, видные по разметке и значениям. Отрезки не пересекаются: у строки
    «Покупатель: ООО «Альфа», ИНН 500100732259» место одно — всё значение."""
    collector = _Collector()
    # Строки в скобках — пояснения составителю бланка: «(должность, ФИО; …)».
    content = [line for line in lines if line.strip() and not line.lstrip().startswith("(")]
    for index, line in enumerate(content):
        _blank_places(line, collector)
        _value_places(line, index, collector)
    fields = collector.fields
    # Место, которое целиком внутри более длинного места того же абзаца, не
    # заменится никогда — такое поле только сбило бы с толку.
    placed = [(f.label, place) for f in fields for place in f.places]
    reachable = {key for line in lines for _, _, key in place_spans(line, placed)}
    return [f for f in fields if f.label in reachable][:limit]
