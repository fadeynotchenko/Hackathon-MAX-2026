"""Места в «рыбе» без помощника: линейки с подписью, реквизиты, даты, «Подпись: значение»."""

from __future__ import annotations

from core.domain.documents import FieldType
from core.domain.places import Place
from core.domain.sample_rules import rule_fields

BLANK_FORM = [
    "ДОГОВОР № ______",
    "г. ____________________        «____» ______________ 20____ г.",
    "(наименование организации или ФИО, ИНН — подсказка составителю)",
    "в лице ______________, действующего на основании ______________,",
    "ИНН / КПП: __________________________",
    "________________ / ________________",
]
FILLED = [
    "Счёт на оплату № 17 от 28.09.2026",
    "Поставщик: ООО «Ромашка», ИНН 7707083893",
    "Покупатель: ООО «Альфа», ИНН 500100732259",
    "ПАО Сбербанк, БИК 044525225, р/с 40702810438000123459",
]


def test_blank_lines_get_their_caption_as_label() -> None:
    fields = {field.label: field for field in rule_fields(BLANK_FORM)}
    assert fields["Номер"].places == [Place("______", "ДОГОВОР № ")]
    assert fields["Город"].places == [Place("____________________", "г. ")]
    assert fields["Дата"].type is FieldType.DATE
    assert fields["В лице"].type is FieldType.NAME
    assert fields["ИНН / КПП"].type is FieldType.TEXT, "двойное значение — не ИНН"
    assert "Действующего на основании" in fields
    assert not any("подсказка" in label for label in fields), "строки в скобках — пояснения"
    assert all(field.value == "" for field in fields.values())
    assert len(fields) == 6, "линейки подписи без подписи рядом не угадываются"


def test_filled_values_become_fields_with_values() -> None:
    fields = rule_fields(FILLED)
    by_label = {field.label: field for field in fields}
    assert by_label["Номер"].key == "number" and by_label["Номер"].value == "17"
    assert by_label["Дата"].key == "date" and by_label["Дата"].value == "28.09.2026"
    assert by_label["Поставщик"].value == "ООО «Ромашка», ИНН 7707083893"
    assert by_label["БИК"].type is FieldType.BIC
    assert by_label["Р/с"].value == "40702810438000123459"
    # ИНН внутри «Поставщик: …» целиком лежит в более длинном месте — такое
    # поле ничего бы не меняло, его нет.
    assert "ИНН" not in by_label
