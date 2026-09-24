"""Инструкции модели и сборка контекста документа.

Граница агента зафиксирована продуктом: он заполняет поля, но не сочиняет
документ; берёт значения только из слов пользователя; не выдаёт ответы за
юридическую экспертизу. Текст инструкций держит эту границу, а проверку
значений всё равно делает домен — модели здесь не доверяют на слово.
"""

from __future__ import annotations

from core.domain.documents import FieldSpec, FieldValue, render_context
from core.usecases.documents import DocumentView

FILL_INSTRUCTIONS = """Ты помощник, который заполняет поля делового документа по сообщению владельца бизнеса.
Правила:
- Заполняй только те поля, значения которых прямо есть в сообщении. Ничего не придумывай и не угадывай.
- Если значения поля в сообщении нет, оставь его пустой строкой.
- Реквизиты (ИНН, КПП, ОГРН, БИК, счёт) переписывай цифра в цифру, без исправлений.
- Суммы пиши числом, даты — в формате ДД.ММ.ГГГГ.
- Если пользователь просит изменить уже заполненное поле, верни новое значение этого поля."""

ASK_INSTRUCTIONS = """Ты помощник по подготовке деловых документов в мессенджере MAX.
Отвечай кратко и по-русски, только про этот документ и его заполнение.
Опирайся на поля и текст документа ниже; чего в них нет, того не утверждай.
Если спрашивают о юридических последствиях, скажи, что это не юридическая консультация,
и посоветуй проверить формулировку у юриста."""

COVER_INSTRUCTIONS = """Напиши короткое сопроводительное сообщение контрагенту к документу во вложении:
3–5 предложений, деловой вежливый тон, по-русски.
Упомяни вид документа и ключевые данные из него (сумму, срок), если они есть.
Не выдумывай имён, дат и условий, которых нет в документе, и не оставляй шаблонных пропусков в скобках."""


def describe_fields(fields: tuple[FieldSpec, ...]) -> str:
    lines = []
    for spec in fields:
        hint = f" ({spec.hint})" if spec.hint else ""
        required = "обязательное" if spec.required else "необязательное"
        lines.append(f"- {spec.key}: {spec.label}, {required}{hint}")
    return "\n".join(lines)


def describe_document(document: DocumentView) -> str:
    context = render_context(document.template.fields, document.values)
    filled = [
        f"- {spec.label}: {context[spec.key]}"
        for spec in document.template.fields
        if context.get(spec.key)
    ]
    labels = {spec.key: spec.label for spec in document.template.fields}
    missing = [labels[key] for key in document.missing]
    return (
        f"Документ: {document.template.title} «{document.title}».\n"
        f"Заполнено:\n{chr(10).join(filled) or '- пока ничего'}\n"
        f"Не заполнено: {', '.join(missing) or 'всё обязательное заполнено'}.\n"
        f"Текст документа:\n{document.preview}"
    )


def fields_schema(fields: tuple[FieldSpec, ...]) -> dict[str, object]:
    """JSON-схема ответа: одно строковое свойство на поле шаблона и ничего сверх."""
    return {
        "type": "object",
        "properties": {spec.key: {"type": "string", "description": spec.label} for spec in fields},
        "additionalProperties": False,
    }


def current_values(fields: tuple[FieldSpec, ...], values: dict[str, FieldValue]) -> str:
    rows = [f"- {spec.key}: {values[spec.key].value}" for spec in fields if spec.key in values]
    return "\n".join(rows) or "- пусто"
