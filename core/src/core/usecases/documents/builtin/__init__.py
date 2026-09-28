"""Стандартные шаблоны: то, с чем продукт открывается у нового пользователя.

Тело шаблона — файл-бланк DOCX из ``blanks/``, сделанный по образцу делового
оборота («рыбе»): счета, КП и договоры в нескольких вариантах. Места для
данных размечены в самом файле маркерами ``{{key}}``, поэтому бланк правится в
Word без кода: маркер — это поле ниже. ``{{key|вариант}}`` — то же значение в
другой записи: сумма прописью, дата словами, НДС по ставке
(``core.domain.documents.fill_context``). Документ собирается в копии бланка,
и PDF получается из неё же — с таблицами, линейками и шрифтами образца.

Первый шаблон каждого вида — основной: его берёт помощник в чате, когда вид
назван без уточнения («счёт на 120 000»).
"""

from ._common import CLIENT, SELLER, SUBJECT, BuiltinTemplate
from .contracts import CONTRACTS, SERVICE_CONTRACT
from .invoices import INVOICE, INVOICES
from .offers import OFFER, OFFERS

BUILTIN_TEMPLATES: tuple[BuiltinTemplate, ...] = (*INVOICES, *OFFERS, *CONTRACTS)
# Основной шаблон вида — для просьбы без уточнения.
MAIN_SLUGS = frozenset({INVOICE.slug, OFFER.slug, SERVICE_CONTRACT.slug})

__all__ = [
    "BUILTIN_TEMPLATES",
    "CLIENT",
    "INVOICE",
    "MAIN_SLUGS",
    "OFFER",
    "SELLER",
    "SERVICE_CONTRACT",
    "SUBJECT",
    "BuiltinTemplate",
]
