"""Реквизиты сторон: единый набор полей для своей компании и для контрагента.

Ключи здесь короткие (``inn``, ``bic``), а в шаблоне те же реквизиты живут с
префиксом стороны (``seller_inn``, ``client_inn``) — по префиксу сценарий
и понимает, откуда подставлять значение.
"""

from __future__ import annotations

from collections.abc import Mapping

from core.domain.documents import FieldSpec, FieldType, FieldValue, validate_fields

SELLER_PREFIX = "seller_"
CLIENT_PREFIX = "client_"

REQUISITE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "Название", FieldType.TEXT, required=True),
    FieldSpec("inn", "ИНН", FieldType.INN, required=False),
    FieldSpec("kpp", "КПП", FieldType.KPP, required=False),
    FieldSpec("ogrn", "ОГРН", FieldType.OGRN, required=False),
    FieldSpec("address", "Адрес", FieldType.ADDRESS, required=False),
    FieldSpec("director", "Подписант", FieldType.NAME, required=False),
    FieldSpec("bank", "Банк", FieldType.TEXT, required=False),
    FieldSpec("bic", "БИК", FieldType.BIC, required=False),
    FieldSpec("account", "Расчётный счёт", FieldType.ACCOUNT, required=False),
    FieldSpec("phone", "Телефон", FieldType.PHONE, required=False),
    FieldSpec("email", "Почта", FieldType.EMAIL, required=False),
)


def validate_requisites(raw: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    """Проверить карточку теми же правилами, что и поля документа."""
    result = validate_fields(REQUISITE_FIELDS, {k: FieldValue(v) for k, v in raw.items()})
    values = {key: value.value for key, value in result.values.items()}
    return values, [error.message for error in result.errors]
