"""Поиск места из ответа модели в тексте образца без различий типографики."""

from __future__ import annotations

from core.domain.places import anchor

LINES = [
    "Исполнитель: ООО «Мастер», ИНН 7707083893",
    "Стоимость работ — 180\xa0000 руб.",
    "Заказчик:   ________",
]


def test_exact_fragment_is_returned_as_is() -> None:
    assert anchor(LINES, "ООО «Мастер»") == "ООО «Мастер»"


def test_fragment_retyped_by_the_model_is_found_as_written_in_the_file() -> None:
    assert anchor(LINES, 'ООО "Мастер"') == "ООО «Мастер»"
    assert anchor(LINES, "180 000") == "180\xa0000", "неразрывный пробел из DOCX"
    assert anchor(LINES, "работ - 180 000") == "работ — 180\xa0000"
    assert anchor(LINES, "Заказчик: ________") == "Заказчик:   ________"


def test_fragment_that_is_not_in_the_file_is_not_found() -> None:
    assert anchor(LINES, "ООО «Гамма»") is None
    assert anchor(LINES, "   ") is None
