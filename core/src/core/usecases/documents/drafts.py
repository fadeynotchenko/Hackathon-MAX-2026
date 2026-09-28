"""Черновик документа: создать, выбрать стороны, заполнить, посмотреть предпросмотр,
взять за основу.

Сценарии каналонейтральны: их одинаково зовут роутер мини-аппа и обработчик
сообщения бота. Значения всегда проходят через ``core.domain.documents``, поэтому
источник (форма, распознанное фото, агент) на правила проверки не влияет.
Создание, переход в «готов» и отклонённые значения ложатся в журнал фактов.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Counterparty, Document
from core.db.repositories import CounterpartyRepository, DocumentRepository
from core.domain.calendar import local_day
from core.domain.documents import (
    FieldError,
    FieldSpec,
    FieldValue,
    ValueSource,
    fill_context,
    fill_text_template,
    validate_fields,
)
from core.domain.exceptions import NotFoundError
from core.usecases.documents.journal import (
    COPY_SOURCE,
    FILE_SOURCE,
    Fact,
    SendState,
    last_sends,
    record,
)
from core.usecases.documents.organizations import seller_for_document
from core.usecases.documents.requisites import CLIENT_PREFIX, SELLER_PREFIX
from core.usecases.documents.templates import (
    TemplateView,
    get_template,
    latest_template,
    to_view,
)

STATUS_DRAFT = "draft"
STATUS_READY = "ready"
# Архив мини-аппа ищет и группирует на клиенте: при пятидесяти старые документы
# пропадали из поиска совсем. Пагинация понадобится, когда их станут тысячи.
ARCHIVE_LIMIT = 500


class Unset(Enum):
    """«Сторону не трогать» — отдельно от ``None``, который значит «отвязать»."""

    UNSET = auto()


UNSET: Final = Unset.UNSET


@dataclass(frozen=True)
class DocumentView:
    id: int
    title: str
    status: str
    template: TemplateView
    counterparty_id: int | None
    organization_id: int | None
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
    # Номер из полей документа: без него в архиве все счета называются одинаково.
    number: str | None
    updated_at: datetime
    created_at: datetime
    sent: SendState | None


def document_name(document: DocumentView) -> str:
    """«Счёт на оплату № 17»: так документ называется в имени файла и в чате —
    одинаковые по виду счета различаются номером."""
    number = document.values.get("number")
    if number is None or number.value in document.title:
        return document.title
    return f"{document.title} № {number.value}"


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
        organization_id=document.organization_id,
        values=validated.values,
        errors=validated.errors + rejected,
        missing=validated.missing,
        unconfirmed=validated.unconfirmed,
        ready=validated.ready,
        preview=fill_text_template(template.body, fill_context(template.fields, validated.values)),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _side_values(
    specs: tuple[FieldSpec, ...],
    prefix: str,
    requisites: Mapping[str, str],
    source: ValueSource,
) -> dict[str, FieldValue]:
    """Поля одной стороны из её карточки: ``seller_inn`` ← ``inn`` организации."""
    values: dict[str, FieldValue] = {}
    for spec in specs:
        if not spec.key.startswith(prefix):
            continue
        filled = requisites.get(spec.key.removeprefix(prefix))
        if filled:
            values[spec.key] = FieldValue(filled, source=source)
    return values


async def _counterparty(
    session: AsyncSession, *, user_id: int, counterparty_id: int
) -> Counterparty:
    counterparty = await CounterpartyRepository(session).get(user_id, counterparty_id)
    if counterparty is None:
        raise NotFoundError("Контрагент не найден", code="counterparty.not_found")
    return counterparty


async def _prefill(
    session: AsyncSession,
    *,
    user_id: int,
    specs: tuple[FieldSpec, ...],
    organization_id: int | None,
    counterparty_id: int | None,
    strict: bool = True,
) -> tuple[dict[str, FieldValue], int | None]:
    """Реквизиты сторон подставляются по префиксу ключа: ``seller_*`` из своей
    организации (выбранной или основной), ``client_*`` из карточки контрагента.
    Возвращает и id организации, чьи реквизиты стоят продавцом."""
    values: dict[str, FieldValue] = {}
    seller = await seller_for_document(
        session, user_id=user_id, organization_id=organization_id, strict=strict
    )
    if seller is not None:
        values |= _side_values(specs, SELLER_PREFIX, seller.values, ValueSource.PROFILE)
    if counterparty_id is not None:
        counterparty = await _counterparty(
            session, user_id=user_id, counterparty_id=counterparty_id
        )
        values |= _side_values(specs, CLIENT_PREFIX, counterparty.values, ValueSource.COUNTERPARTY)
    today = local_day(datetime.now(UTC)).isoformat()
    for spec in specs:
        if spec.key in values:
            continue
        if spec.today_by_default:
            values[spec.key] = FieldValue(today, source=ValueSource.DEFAULT)
        elif spec.default:
            values[spec.key] = FieldValue(spec.default, source=ValueSource.DEFAULT)
    return values, seller.id if seller is not None else None


async def create_draft(
    session: AsyncSession,
    *,
    user_id: int,
    template_id: int,
    counterparty_id: int | None = None,
    organization_id: int | None = None,
    title: str = "",
) -> DocumentView:
    template = await get_template(session, user_id=user_id, template_id=template_id)
    return await _create(
        session,
        user_id=user_id,
        template=template,
        counterparty_id=counterparty_id,
        organization_id=organization_id,
        title=title,
    )


async def create_from_values(
    session: AsyncSession,
    *,
    user_id: int,
    template: TemplateView,
    values: Mapping[str, FieldValue],
    title: str = "",
) -> DocumentView:
    """Документ по присланному файлу: значения — то, что стоит в файле. Пустые
    места дополняются как у нового документа — реквизиты своей организации,
    значения по умолчанию. Значение из файла, не прошедшее проверку (ИНН с
    неверной контрольной суммой), в документ не попадает, а ошибка видна."""
    return await _create(
        session, user_id=user_id, template=template, initial=values, title=title, source=FILE_SOURCE
    )


async def _create(
    session: AsyncSession,
    *,
    user_id: int,
    template: TemplateView,
    counterparty_id: int | None = None,
    organization_id: int | None = None,
    title: str = "",
    initial: Mapping[str, FieldValue] | None = None,
    source: str | None = None,
) -> DocumentView:
    values, seller_id = await _prefill(
        session,
        user_id=user_id,
        specs=template.fields,
        organization_id=organization_id,
        counterparty_id=counterparty_id,
    )
    values |= dict(initial or {})
    validated = validate_fields(template.fields, values)
    document = await DocumentRepository(session).create(
        user_id,
        template_id=template.id,
        counterparty_id=counterparty_id,
        organization_id=seller_id,
        title=title.strip() or template.title,
        values=dump_values(validated.values),
    )
    await record(
        session,
        user_id=user_id,
        kind=Fact.CREATED,
        document_id=document.id,
        template_kind=template.kind,
        source=source,
    )
    rejected = tuple(error for error in validated.errors if error.key in (initial or {}))
    return _view(document, template, rejected=rejected)


async def copy_document(
    session: AsyncSession, *, user_id: int, document_id: int, title: str | None = None
) -> DocumentView:
    """Новый черновик на основе прошлого документа: те же условия и стороны.

    Реквизиты сторон берутся заново из той же организации и карточки контрагента —
    они могли измениться с прошлого раза; удалённую организацию заменяет основная.
    Поля с ``carry_over=False`` (номер, даты) не переносятся: у нового документа
    они свои. Свой шаблон, который с тех пор правили, берётся в новой редакции."""
    source = await _load(session, user_id=user_id, document_id=document_id)
    template = await latest_template(session, source.template)
    carried = {spec.key for spec in template.fields if spec.carry_over}
    values = {key: v for key, v in load_values(source.values).items() if key in carried}
    prefilled, seller_id = await _prefill(
        session,
        user_id=user_id,
        specs=template.fields,
        organization_id=source.organization_id,
        counterparty_id=source.counterparty_id,
        strict=False,
    )
    values = _without_stale_requisites(
        values,
        seller_changed=seller_id != source.organization_id,
        has_counterparty=source.counterparty_id is not None,
    )
    values |= prefilled
    validated = validate_fields(template.fields, values)
    document = await DocumentRepository(session).create(
        user_id,
        template_id=template.id,
        counterparty_id=source.counterparty_id,
        organization_id=seller_id,
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


def _without_stale_requisites(
    values: Mapping[str, FieldValue], *, seller_changed: bool, has_counterparty: bool
) -> dict[str, FieldValue]:
    """Реквизиты сторон в копии — только свежие, без примеси старых.

    Подставленное из организации или карточки перечитывается заново: поле,
    которое там стёрли, не должно доехать из прошлого документа. Если продавец
    сменился (организацию удалили — копия идёт от основной), уходят все его
    поля: иначе КПП и счёт удалённой организации встали бы рядом с названием
    основной. Карточки клиента нет — его значения остаются как были в документе."""

    def stale(key: str, value: FieldValue) -> bool:
        if key.startswith(SELLER_PREFIX):
            return seller_changed or value.source is ValueSource.PROFILE
        if key.startswith(CLIENT_PREFIX):
            return has_counterparty and value.source is ValueSource.COUNTERPARTY
        return False

    return {key: value for key, value in values.items() if not stale(key, value)}


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
    previous = load_values(document.values)
    validated = validate_fields(template.fields, values)
    incoming = incoming or {}
    rejected = tuple(error for error in validated.errors if error.key in incoming)
    # Сверка счёта с БИК пропускает оба значения по отдельности, поэтому
    # отклонённое убираем явно: иначе счёт остался бы в документе рядом с ошибкой о нём.
    rejected_keys = {error.key for error in rejected}
    kept = {key: value for key, value in validated.values.items() if key not in rejected_keys}
    # Отклонённая правка не стирает прежнее верное значение: «сумма 150 тыщ» с
    # ошибкой оставляет в документе прошлую сумму, а ошибку показывает рядом.
    kept |= {key: previous[key] for key in rejected_keys if key in previous}
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


def _switch_side(
    values: Mapping[str, FieldValue],
    specs: tuple[FieldSpec, ...],
    prefix: str,
    source: ValueSource,
    requisites: Mapping[str, str] | None,
) -> dict[str, FieldValue]:
    """Поля одной стороны после выбора в форме.

    Выбрали организацию или карточку — уходят все поля стороны, даже набранные
    руками, и встают её реквизиты: иначе КПП и счёт прежней стороны остались бы
    рядом с новым названием (то же, что в ``_without_stale_requisites``).
    Отвязали (``None``) — уходит только подставленное из справочника, набранное
    человеком остаётся."""
    kept = {
        key: value
        for key, value in values.items()
        if not key.startswith(prefix) or (requisites is None and value.source is not source)
    }
    if requisites is not None:
        kept |= _side_values(specs, prefix, requisites, source)
    return kept


async def set_parties(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    organization_id: int | Unset | None = UNSET,
    counterparty_id: int | Unset | None = UNSET,
) -> DocumentView:
    """Выбрать в форме, от кого и кому документ, — уже после создания черновика.

    Id — своя организация или карточка контрагента: её реквизиты встают целиком.
    ``None`` — отвязать, ``UNSET`` — сторону не трогать. Остальные поля не
    меняются, дату по умолчанию заново не ставим: её могли исправить руками."""
    document = await _load(session, user_id=user_id, document_id=document_id)
    template = to_view(document.template)
    if organization_id is UNSET and counterparty_id is UNSET:
        return _view(document, template)
    # Обе стороны ищем до правок: чужой id отвечает 404, не тронув документ.
    seller = None
    if isinstance(organization_id, int):
        seller = await seller_for_document(
            session, user_id=user_id, organization_id=organization_id
        )
    counterparty = None
    if isinstance(counterparty_id, int):
        counterparty = await _counterparty(
            session, user_id=user_id, counterparty_id=counterparty_id
        )

    values = load_values(document.values)
    if organization_id is not UNSET:
        values = _switch_side(
            values,
            template.fields,
            SELLER_PREFIX,
            ValueSource.PROFILE,
            seller.values if seller is not None else None,
        )
        document.organization_id = seller.id if seller is not None else None
    if counterparty_id is not UNSET:
        values = _switch_side(
            values,
            template.fields,
            CLIENT_PREFIX,
            ValueSource.COUNTERPARTY,
            counterparty.values if counterparty is not None else None,
        )
        # Связь загружена вместе с документом и за counterparty_id сама не следует:
        # без присваивания объект в этой сессии помнил бы прежнюю карточку.
        document.counterparty = counterparty
        document.counterparty_id = counterparty.id if counterparty is not None else None
    saved, _rejected = await _save(session, document, template, values)
    return _view(saved, template)


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
    return _raw_value(document, f"{CLIENT_PREFIX}name")


def _raw_value(document: Document, key: str) -> str | None:
    item = document.values.get(key) or {}
    return str(item.get("value") or "") or None


async def list_documents(
    session: AsyncSession, *, user_id: int, limit: int = ARCHIVE_LIMIT
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
            number=_raw_value(document, "number"),
            updated_at=document.updated_at,
            created_at=document.created_at,
            sent=sends.get(document.id),
        )
        for document in documents
    ]
