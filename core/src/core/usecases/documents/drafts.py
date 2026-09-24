"""Черновик документа: создать, заполнить, посмотреть предпросмотр, взять за основу.

Сценарии каналонейтральны: их одинаково зовут роутер мини-аппа и обработчик
сообщения бота. Значения всегда проходят через ``core.domain.documents``, поэтому
источник (форма, распознанное фото, агент) на правила проверки не влияет.
Создание, переход в «готов» и отклонённые значения ложатся в журнал фактов.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Document
from core.db.repositories import (
    CompanyProfileRepository,
    CounterpartyRepository,
    DocumentRepository,
)
from core.domain.documents import (
    FieldError,
    FieldSpec,
    FieldValue,
    ValueSource,
    fill_text_template,
    render_context,
    validate_fields,
)
from core.domain.exceptions import NotFoundError
from core.usecases.documents.journal import COPY_SOURCE, Fact, SendState, last_sends, record
from core.usecases.documents.requisites import CLIENT_PREFIX, SELLER_PREFIX
from core.usecases.documents.templates import TemplateView, get_template, to_view

STATUS_DRAFT = "draft"
STATUS_READY = "ready"


@dataclass(frozen=True)
class DocumentView:
    id: int
    title: str
    status: str
    template: TemplateView
    counterparty_id: int | None
    values: dict[str, FieldValue]
    errors: tuple[FieldError, ...]
    missing: tuple[str, ...]
    unconfirmed: tuple[str, ...]
    ready: bool
    preview: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DocumentSummary:
    id: int
    title: str
    status: str
    template_title: str
    counterparty_name: str | None
    # Кому документ: карточка контрагента или название клиента из полей.
    client: str | None
    updated_at: datetime
    created_at: datetime
    sent: SendState | None


def dump_values(values: Mapping[str, FieldValue]) -> dict[str, dict[str, object]]:
    return {
        key: {
            "value": value.value,
            "source": value.source.value,
            "confidence": value.confidence,
            "confirmed": value.confirmed,
            "fragment": value.fragment,
        }
        for key, value in values.items()
    }


def load_values(raw: Mapping[str, dict[str, object]]) -> dict[str, FieldValue]:
    out: dict[str, FieldValue] = {}
    for key, item in raw.items():
        confidence = item.get("confidence")
        fragment = item.get("fragment")
        out[key] = FieldValue(
            value=str(item.get("value", "")),
            source=ValueSource(str(item.get("source", ValueSource.MANUAL))),
            confidence=float(confidence) if confidence is not None else None,
            confirmed=bool(item.get("confirmed", True)),
            fragment=str(fragment) if fragment else None,
        )
    return out


def _view(
    document: Document, template: TemplateView, *, rejected: tuple[FieldError, ...] = ()
) -> DocumentView:
    """Ошибки отклонённых значений приходят снаружи: в документе их уже нет,
    но пользователю надо объяснить, почему поле осталось пустым."""
    validated = validate_fields(template.fields, load_values(document.values))
    return DocumentView(
        id=document.id,
        title=document.title,
        status=document.status,
        template=template,
        counterparty_id=document.counterparty_id,
        values=validated.values,
        errors=validated.errors + rejected,
        missing=validated.missing,
        unconfirmed=validated.unconfirmed,
        ready=validated.ready,
        preview=fill_text_template(
            template.body, render_context(template.fields, validated.values)
        ),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


async def _prefill(
    session: AsyncSession,
    *,
    user_id: int,
    specs: tuple[FieldSpec, ...],
    counterparty_id: int | None,
) -> dict[str, FieldValue]:
    """Реквизиты сторон подставляются по префиксу ключа: ``seller_*`` из своей
    карточки, ``client_*`` из карточки контрагента."""
    values: dict[str, FieldValue] = {}
    profile = await CompanyProfileRepository(session).get(user_id)
    sources: list[tuple[str, Mapping[str, str], ValueSource]] = []
    if profile is not None:
        sources.append((SELLER_PREFIX, profile.values, ValueSource.PROFILE))
    if counterparty_id is not None:
        counterparty = await CounterpartyRepository(session).get(user_id, counterparty_id)
        if counterparty is None:
            raise NotFoundError("Контрагент не найден", code="counterparty.not_found")
        sources.append((CLIENT_PREFIX, counterparty.values, ValueSource.COUNTERPARTY))

    for spec in specs:
        for prefix, requisites, source in sources:
            if not spec.key.startswith(prefix):
                continue
            filled = requisites.get(spec.key.removeprefix(prefix))
            if filled:
                values[spec.key] = FieldValue(filled, source=source)
    return values


async def create_draft(
    session: AsyncSession,
    *,
    user_id: int,
    template_id: int,
    counterparty_id: int | None = None,
    title: str = "",
) -> DocumentView:
    template = await get_template(session, user_id=user_id, template_id=template_id)
    values = await _prefill(
        session, user_id=user_id, specs=template.fields, counterparty_id=counterparty_id
    )
    validated = validate_fields(template.fields, values)
    document = await DocumentRepository(session).create(
        user_id,
        template_id=template.id,
        counterparty_id=counterparty_id,
        title=title.strip() or template.title,
        values=dump_values(validated.values),
    )
    await record(
        session,
        user_id=user_id,
        kind=Fact.CREATED,
        document_id=document.id,
        template_kind=template.kind,
    )
    return _view(document, template)


async def copy_document(
    session: AsyncSession, *, user_id: int, document_id: int, title: str | None = None
) -> DocumentView:
    """Новый черновик на основе прошлого документа: те же условия и стороны.

    Реквизиты сторон берутся заново из профиля и карточки контрагента — они могли
    измениться с прошлого раза. Поля с ``carry_over=False`` (номер, даты) не
    переносятся: у нового документа они свои."""
    source = await _load(session, user_id=user_id, document_id=document_id)
    template = to_view(source.template)
    carried = {spec.key for spec in template.fields if spec.carry_over}
    values = {key: v for key, v in load_values(source.values).items() if key in carried}
    values |= await _prefill(
        session,
        user_id=user_id,
        specs=template.fields,
        counterparty_id=source.counterparty_id,
    )
    validated = validate_fields(template.fields, values)
    document = await DocumentRepository(session).create(
        user_id,
        template_id=template.id,
        counterparty_id=source.counterparty_id,
        title=(title or "").strip() or source.title,
        values=dump_values(validated.values),
    )
    await record(
        session,
        user_id=user_id,
        kind=Fact.CREATED,
        document_id=document.id,
        template_kind=template.kind,
        source=COPY_SOURCE,
    )
    return _view(document, template)


async def _load(session: AsyncSession, *, user_id: int, document_id: int) -> Document:
    document = await DocumentRepository(session).get(user_id, document_id)
    if document is None:
        raise NotFoundError("Документ не найден", code="document.not_found")
    return document


async def get_document(session: AsyncSession, *, user_id: int, document_id: int) -> DocumentView:
    document = await _load(session, user_id=user_id, document_id=document_id)
    return _view(document, to_view(document.template))


async def _save(
    session: AsyncSession,
    document: Document,
    template: TemplateView,
    values: Mapping[str, FieldValue],
    *,
    incoming: Mapping[str, FieldValue] | None = None,
) -> tuple[Document, tuple[FieldError, ...]]:
    """Сохранить значения и записать факты: переход в «готов» и отклонённое.

    Статус считается по тому, что сохранено: отклонённое значение в документ не
    попадает и готовность не портит. Отклонённым считается только пришедшее
    сейчас (``incoming``): ошибка уже лежащего значения — не новая пойманная,
    её покажет ``_view`` по сохранённому. Возвращаются только отклонённые."""
    was_ready = document.status == STATUS_READY
    validated = validate_fields(template.fields, values)
    incoming = incoming or {}
    rejected = tuple(error for error in validated.errors if error.key in incoming)
    # Сверка счёта с БИК пропускает оба значения по отдельности, поэтому
    # отклонённое убираем явно: иначе счёт остался бы в документе рядом с ошибкой о нём.
    rejected_keys = {error.key for error in rejected}
    kept = {key: value for key, value in validated.values.items() if key not in rejected_keys}
    ready = validate_fields(template.fields, kept).ready
    saved = await DocumentRepository(session).save_values(
        document,
        dump_values(kept),
        status=STATUS_READY if ready else STATUS_DRAFT,
    )
    if ready and not was_ready:
        await record(
            session,
            user_id=saved.user_id,
            kind=Fact.READY,
            document_id=saved.id,
            template_kind=template.kind,
        )
    for error in rejected:
        await record(
            session,
            user_id=saved.user_id,
            kind=Fact.REJECTED,
            document_id=saved.id,
            template_kind=template.kind,
            code=error.code,
            source=incoming[error.key].source.value,
        )
    return saved, rejected


async def set_fields(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    values: Mapping[str, FieldValue],
    title: str | None = None,
) -> DocumentView:
    """Проставить значения поверх уже заполненных. Пустая строка стирает поле:
    иначе ошибочно распознанный реквизит нельзя было бы убрать из документа."""
    document = await _load(session, user_id=user_id, document_id=document_id)
    template = to_view(document.template)
    merged = load_values(document.values) | dict(values)
    if title is not None and title.strip():
        document.title = title.strip()
    saved, errors = await _save(session, document, template, merged, incoming=values)
    return _view(saved, template, rejected=errors)


async def confirm_fields(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    keys: Sequence[str] | None = None,
) -> DocumentView:
    """Человек утвердил значения, предложенные агентом или распознанные с фото.

    ``keys=None`` подтверждает все ждущие значения разом — так работает кнопка
    «всё верно» в чате; список ключей — выборочная проверка в форме.
    """
    document = await _load(session, user_id=user_id, document_id=document_id)
    template = to_view(document.template)
    values = load_values(document.values)
    wanted = set(values) if keys is None else set(keys)
    confirmed = {
        key: replace(value, confirmed=True) if key in wanted else value
        for key, value in values.items()
    }
    saved, _errors = await _save(session, document, template, confirmed)
    return _view(saved, template)


async def delete_document(session: AsyncSession, *, user_id: int, document_id: int) -> None:
    """Удалить документ вместе с записями о собранных файлах (каскад в БД).

    Сами файлы на диске остаются сиротами: чистка каталога — отдельная задача,
    а держать её в удалении значит выносить путь хранилища в сценарий.
    """
    document = await _load(session, user_id=user_id, document_id=document_id)
    await DocumentRepository(session).delete(document)


def _client(document: Document) -> str | None:
    if document.counterparty is not None:
        return document.counterparty.name
    name = document.values.get(f"{CLIENT_PREFIX}name") or {}
    return str(name.get("value") or "") or None


async def list_documents(
    session: AsyncSession, *, user_id: int, limit: int = 50
) -> list[DocumentSummary]:
    """История: что, кому и когда отправлено, чем кончилась доставка."""
    documents = await DocumentRepository(session).list_for_user(user_id, limit=limit)
    sends = await last_sends(session, [document.id for document in documents])
    return [
        DocumentSummary(
            id=document.id,
            title=document.title,
            status=document.status,
            template_title=document.template.title,
            counterparty_name=document.counterparty.name if document.counterparty else None,
            client=_client(document),
            updated_at=document.updated_at,
            created_at=document.created_at,
            sent=sends.get(document.id),
        )
        for document in documents
    ]
