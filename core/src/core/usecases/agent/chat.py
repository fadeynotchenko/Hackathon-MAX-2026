"""Диалог с помощником в чате бота: сообщение, вложение или нажатая кнопка → ответ с кнопками.

Сценарий не знает про MAX и Redis: на вход — кто написал и что, на выход —
текст и кнопки, которые канал доставит сам. Документ, над которым идёт работа,
запоминается в ``chat_states``: пользователь пишет «поменяй срок на 10 дней»,
не называя документ.

Вложение (фото, скан, голосовое) приходит ссылкой, байты сценарий получает
через ``ChatActionDeps.download``. Голосовое расшифровывается и дальше живёт
как обычное сообщение. Фото без текущего документа откладывается: помощник
спрашивает, для какого документа его распознать, и берёт файл по нажатию.

Кнопки несут действие строкой ``doc:<действие>[:<id>[:<формат>]]``: нажатие
приходит обратно в ядро, и права проверяются заново — строка из кнопки не
доверенная, документ ищется только среди документов нажавшего.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import PurePosixPath

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import (
    ChatStateRepository,
    DownloadTokenRepository,
    UserRepository,
    UserUpsert,
)
from core.domain.documents import render_context
from core.domain.exceptions import AppError, NotFoundError
from core.domain.media import AUDIBLE, MediaKind
from core.events import EventBus
from core.files import FilesConfig, InboundFileError, InboundFileTooLargeError, fetch_media
from core.llm import ChatMessage, LLMClient, LLMError
from core.logs import biz_warn
from core.usecases.agent.recognize import fill_from_file, transcribe
from core.usecases.agent.service import (
    AgentFillResult,
    answer_question,
    fill_from_message,
    lower_first,
    missing_labels,
    missing_text,
)
from core.usecases.documents import (
    DocumentView,
    OrganizationView,
    TemplateView,
    confirm_fields,
    copy_document,
    create_draft,
    document_name,
    get_document,
    last_sends,
    list_organizations,
    list_templates,
    send_document_to_chat,
)
from core.usecases.users import mark_active

# Ответы в чат — HTML MAX (бот отправляет их с format="html"). Всё, что пришло от
# человека, модели или из шаблона, проходит через _esc: иначе «ООО <Ромашка>» или
# «&» в названии сломали бы разметку, и MAX не принял бы сообщение.
DISABLED_TEXT = (
    "🔌 Помощник сейчас выключен.\n"
    "Документ можно заполнить в мини-приложении: /start → «Создать документ»."
)
ASK_TEMPLATE_TEXT = (
    "📄 <b>Какой документ подготовить?</b>\n"
    "Выберите ниже 👇 или опишите словами, например:\n"
    "<i>«Счёт на 120 000 для ООО Ромашка за разработку сайта»</i>"
)
ASK_MEDIA_TEMPLATE_TEXT = (
    "📎 <b>Куда перенести данные из вложения?</b>\n"
    "Выберите документ 👇 — распознаю и покажу, что нашёл."
)
UNKNOWN_BUTTON_TEXT = "⌛ Эта кнопка больше не работает. Напишите, что нужно сделать."
LLM_DOWN_TEXT = (
    "😔 Помощник не отвечает.\nПопробуйте через минуту или заполните документ в приложении."
)
MEDIA_EXPIRED_TEXT = "⌛ Вложение, присланное раньше, устарело — пришлите его ещё раз."
MEDIA_OFFER_TEXT = "📎 Взять данные и из присланного раньше вложения? Нажмите «Взять из вложения»."
DOWNLOAD_FAILED_TEXT = "😔 Не получилось скачать вложение из MAX — пришлите его ещё раз."
UNSUPPORTED_FILE_TEXT = "🤔 Такой файл я не прочитаю.\nПодойдёт фото, PDF, DOCX или голосовое."
READY_TEXT = "🏁 <b>Документ готов!</b> В каком формате прислать файл?"
HOW_TO_FILL_TEXT = (
    "Как удобнее:\n"
    "✍️ напишите одним сообщением\n"
    "🎙 надиктуйте голосовым\n"
    "📷 пришлите фото карточки клиента"
)

CONFIRM_BUTTON = "👍 Всё верно"
SEND_DOCX_BUTTON = "📘 Прислать DOCX"
SEND_PDF_BUTTON = "📕 Прислать PDF"
NEW_BUTTON = "➕ Новый документ"
COPY_BUTTON = "📑 На основе этого"
MEDIA_BUTTON = "📎 Взять из вложения"
# Значок вида документа в заголовке ответа и на кнопке шаблона; свой вид — 📄.
_KIND_ICONS = {"invoice": "🧾", "offer": "💼", "contract": "🤝"}
# Предел текста кнопки в контракте notify.user.
_BUTTON_LIMIT = 64

# Сколько отложенное фото ждёт выбора документа: дальше ссылка MAX может протухнуть,
# а пользователь — забыть, что присылал.
PENDING_MEDIA_TTL = timedelta(minutes=30)
TRANSCRIPT_PREVIEW_LENGTH = 500
_READABLE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".pdf", ".docx"}
)
_AUDIBLE_SUFFIXES = frozenset({".ogg", ".oga", ".opus", ".mp3", ".m4a", ".mp4", ".wav", ".weba"})

ROUTE_INSTRUCTIONS = """Определи, чего хочет пользователь в чате с помощником по документам.
intent:
- new — подготовить новый документ (укажи его вид в template);
- fill — дописать или поправить текущий документ; сюда же значения без вопроса —
  числа, даты, ФИО, реквизиты, в том числе столбиком или через запятую;
- question — человек спрашивает о текущем документе и ничего не присылает для заполнения.
Если текущего документа нет, запрос на заполнение означает new.
template — вид нового документа из списка ниже или пустая строка, если вид не ясен."""

MediaFetcher = Callable[[str], Awaitable[bytes]]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatSender:
    max_user_id: int
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None


@dataclass(frozen=True)
class ChatButton:
    text: str
    payload: str


@dataclass(frozen=True)
class ChatReply:
    """Ответ в чат. ``text`` — HTML MAX: канал отправляет его с разметкой."""

    text: str
    buttons: tuple[tuple[ChatButton, ...], ...] = ()


@dataclass(frozen=True)
class ChatAttachment:
    """Вложение из чата: вид по MAX (image, file, audio), ссылка и подпись к нему."""

    kind: str
    url: str
    filename: str | None = None
    caption: str | None = None


@dataclass(frozen=True)
class ChatActionDeps:
    """Всё, что нужно кнопкам и вложениям: сборка файла, событие боту, одноразовый
    токен, модель и скачивание вложения (``fetch`` подменяют тесты)."""

    files: FilesConfig
    bus: EventBus
    tokens: DownloadTokenRepository
    llm: LLMClient | None = None
    fetch: MediaFetcher | None = None

    async def download(self, url: str) -> bytes:
        if self.fetch is not None:
            return await self.fetch(url)
        return await fetch_media(
            url,
            max_bytes=self.files.media_max_bytes,
            timeout_seconds=self.files.media_timeout_seconds,
        )


def _esc(text: str) -> str:
    return escape(text, quote=False)


def _bullets(items: Iterable[str]) -> str:
    return "\n".join(f"• {item}" for item in items)


def _failure_text(exc: AppError) -> str:
    """Текст ошибки для чата. Сбой на нашей стороне или у модели (5xx) пишется в лог:
    в HTTP это делает обработчик ошибок api, а у событий бота его нет."""
    if exc.status_code >= 500:
        biz_warn(logger, "agent.chat.failed", code=exc.code, error=exc.log_message or str(exc))
    if exc.code == "agent.unavailable":
        return LLM_DOWN_TEXT
    return f"😔 {_esc(exc.public_message)}"


def _icon(kind: str) -> str:
    return _KIND_ICONS.get(kind, "📄")


def _template_buttons(templates: list[TemplateView]) -> tuple[tuple[ChatButton, ...], ...]:
    return tuple(
        (ChatButton(f"{_icon(t.kind)} {t.title}"[:_BUTTON_LIMIT], f"doc:new:{t.slug}"),)
        for t in templates
    )


def _document_buttons(document: DocumentView) -> tuple[tuple[ChatButton, ...], ...]:
    rows: list[tuple[ChatButton, ...]] = []
    if document.unconfirmed:
        rows.append((ChatButton(CONFIRM_BUTTON, f"doc:confirm:{document.id}"),))
    elif document.ready:
        rows.append(
            (
                ChatButton(SEND_DOCX_BUTTON, f"doc:send:{document.id}:docx"),
                ChatButton(SEND_PDF_BUTTON, f"doc:send:{document.id}:pdf"),
            )
        )
    rows.append((ChatButton(NEW_BUTTON, "doc:new"),))
    return tuple(rows)


def _heading(document: DocumentView) -> str:
    """«Счёт на оплату № 17»; своё название — вместе с видом документа."""
    if document.title != document.template.title:
        return f"{document.template.title} «{document.title}»"
    return document_name(document)


def _title_line(document: DocumentView) -> str:
    """Первая строка ответа о документе: значок вида и название жирным."""
    return f"{_icon(document.template.kind)} <b>{_esc(_heading(document))}</b>"


def _missing_block(document: DocumentView, title: str = "Ещё нужно") -> str:
    return f"📋 <b>{title}:</b>\n" + _bullets(_esc(label) for label in missing_labels(document))


def _fill_text(
    result: AgentFillResult, *, source: str = "В сообщении", seller: str | None = None
) -> str:
    """Ответ показывает значения, а не только названия полей: подтверждать
    человек должен то, что увидел, а не то, что помощник пообещал заполнить.

    Разделы — заголовок, записанное, замечания, недостающее, что делать дальше —
    отделены пустой строкой: в длинном ответе значения ищут глазами."""
    document = result.document
    context = render_context(document.template.fields, document.values)
    labels = {spec.key: spec.label for spec in document.template.fields}
    head = [_title_line(document)]
    if seller:
        head.append(f"🏢 От: {_esc(seller)}")
    if result.kind:
        head.append(f"📎 Во вложении — {_esc(result.kind)}.")
    blocks = ["\n".join(head)]
    written = [
        f"• {_esc(labels[key])}: <b>{_esc(context[key])}</b>"
        for key in result.filled
        if context.get(key)
    ]
    notes: list[str] = []
    if written:
        blocks.append("✍️ <b>Записал:</b>\n" + "\n".join(written))
    elif result.unchanged and not result.rejected:
        same = ", ".join(lower_first(labels[key]) for key in result.unchanged)
        notes.append(f"👌 Ничего не поменял — в документе уже так: {_esc(same)}.")
    elif not result.rejected:
        notes.append(f"🤔 {source} не нашёл значений для полей документа.")
    if result.kept:
        kept = ", ".join(lower_first(labels[key]) for key in result.kept)
        notes.append(f"↩️ Не стал менять — во вложении другое: {_esc(kept)}.")
    if notes:
        blocks.append("\n".join(notes))
    if result.rejected:
        blocks.append(
            "❗ <b>Не записал:</b>\n" + _bullets(_esc(error.message) for error in result.rejected)
        )
    rejected = {error.key for error in result.rejected}
    # Ошибка уже записанного значения (счёт не сходится с новым БИК) — тоже сюда,
    # иначе «Всё верно» подтвердит, а документ так и не станет готовым.
    problems = [error.message for error in document.errors if error.key not in rejected]
    if problems:
        blocks.append("❗ <b>Проверьте:</b>\n" + _bullets(_esc(problem) for problem in problems))
    if document.missing:
        blocks.append(_missing_block(document))
    if document.unconfirmed:
        blocks.append("👉 Проверьте значения и нажмите «Всё верно».")
    elif document.ready:
        blocks.append(READY_TEXT)
    return "\n\n".join(blocks)


def _confirm_text(document: DocumentView) -> str:
    if document.ready:
        return READY_TEXT
    if document.missing:
        return (
            f"👍 Подтвердил.\n\n{_missing_block(document)}\n\n"
            "Напишите недостающее сообщением или надиктуйте голосовым."
        )
    if not document.errors:
        return "👍 Подтвердил."
    problems = _bullets(_esc(error.message) for error in document.errors)
    return (
        f"👍 Подтвердил, но есть ошибки:\n{problems}\n\nПоправьте их сообщением или в приложении."
    )


def _download_error_text(exc: InboundFileError, files: FilesConfig) -> str:
    if isinstance(exc, InboundFileTooLargeError):
        return f"😔 Файл больше {files.media_max_bytes // (1024 * 1024)} МБ — пришлите поменьше."
    return DOWNLOAD_FAILED_TEXT


def _readable_kind(attachment: ChatAttachment) -> MediaKind | None:
    """Вид вложения по данным MAX, до скачивания: файл с чужим расширением не качаем.
    Окончательно тип проверяет домен по содержимому."""
    if attachment.kind == "image":
        return MediaKind.IMAGE
    if attachment.kind == "audio":
        return MediaKind.AUDIO
    suffix = PurePosixPath((attachment.filename or "").lower()).suffix
    if suffix in _READABLE_SUFFIXES:
        return MediaKind.DOCUMENT
    if suffix in _AUDIBLE_SUFFIXES:
        return MediaKind.AUDIO
    return None


async def _ensure_user(session: AsyncSession, sender: ChatSender) -> int:
    now = datetime.now(UTC)
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(
            max_user_id=sender.max_user_id,
            first_name=sender.first_name,
            last_name=sender.last_name,
            username=sender.username,
            via="bot",
        ),
        touch_login=False,
        now=now,
    )
    await mark_active(session, user.id, now=now)
    return user.id


async def _active_document(session: AsyncSession, user_id: int) -> DocumentView | None:
    document_id = await ChatStateRepository(session).active_document_id(user_id)
    if document_id is None:
        return None
    try:
        return await get_document(session, user_id=user_id, document_id=document_id)
    except NotFoundError:
        return None


async def _route(
    llm: LLMClient, text: str, active: DocumentView | None, templates: list[TemplateView]
) -> tuple[str, str]:
    catalog = "\n".join(f"- {t.slug}: {t.title}" for t in templates)
    current = (
        f"{_heading(active)}, ждёт значений: {missing_text(active) or 'нет'}" if active else "нет"
    )
    schema = {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ["new", "fill", "question"]},
            "template": {"type": "string", "enum": [*(t.slug for t in templates), ""]},
        },
        "required": ["intent", "template"],
        "additionalProperties": False,
    }
    raw = await llm.complete_json(
        [
            ChatMessage(
                "system",
                f"{ROUTE_INSTRUCTIONS}\n\nВиды документов:\n{catalog}\n\nТекущий документ: {current}",
            ),
            ChatMessage("user", text),
        ],
        schema=schema,
    )
    return str(raw.get("intent", "fill")), str(raw.get("template", ""))


# Слова организационно-правовой формы есть в названии почти любой организации:
# по ним своя организация не опознаётся.
_LEGAL_FORM_STEMS = frozenset({"обще", "огра", "отве", "инди", "пред", "акци", "публ", "закр"})
_NAME_WORD = re.compile(r"[0-9a-zа-я]+(?:-[0-9a-zа-я]+)*")
# Сколько букв в конце слова может поменять падеж: «Ромашка» → «Ромашкой».
_CASE_ENDING = 2
_MIN_STEM = 4


def _name_words(text: str) -> list[str]:
    return _NAME_WORD.findall(text.lower().replace("ё", "е"))


def _same_word(name_word: str, said: str) -> bool:
    """Слово названия и слово сообщения — одно и то же с точностью до падежа.

    Четырёх общих букв мало: «строительные» совпадало со «Стройпроект», а клиент
    «Ромашка-Сервис» — со своей «Ромашкой». Нужна вся основа слова, и слово
    сообщения не может быть намного длиннее."""
    stem = max(_MIN_STEM, len(name_word) - _CASE_ENDING)
    return said.startswith(name_word[:stem]) and len(said) <= len(name_word) + 3


def named_organization(organizations: list[OrganizationView], text: str) -> int | None:
    """Своя организация, названная в сообщении: «счёт от ИП Нотченко». Если названы
    две или ни одной — не угадываем, документ пойдёт от основной."""
    said = _name_words(text)
    named = []
    for organization in organizations:
        words = [
            word
            for word in _name_words(organization.name)
            if len(word) >= _MIN_STEM and word[:_MIN_STEM] not in _LEGAL_FORM_STEMS
        ]
        if any(_same_word(word, other) for word in words for other in said):
            named.append(organization.id)
    return named[0] if len(named) == 1 else None


@dataclass(frozen=True)
class _Started:
    document: DocumentView
    # Своих организаций несколько: ответ называет, от какой документ, — выбор
    # по словам сообщения человек должен видеть.
    seller: str | None


async def _start_document(
    session: AsyncSession, user_id: int, template_id: int, text: str = ""
) -> _Started:
    organization_id = None
    organizations = await list_organizations(session, user_id=user_id)
    if text and len(organizations) > 1:
        organization_id = named_organization(organizations, text)
    document = await create_draft(
        session, user_id=user_id, template_id=template_id, organization_id=organization_id
    )
    await ChatStateRepository(session).set_active_document(user_id, document.id)
    seller = next((o.name for o in organizations if o.id == document.organization_id), None)
    return _Started(document, seller if len(organizations) > 1 else None)


async def handle_chat_message(
    session: AsyncSession, *, sender: ChatSender, text: str, llm: LLMClient | None
) -> ChatReply:
    user_id = await _ensure_user(session, sender)
    if llm is None:
        return ChatReply(DISABLED_TEXT)
    chat = ChatStateRepository(session)
    templates = await list_templates(session, user_id=user_id)
    active = await _active_document(session, user_id)
    started: _Started | None = None
    # Новый документ создаётся до вызова модели; если модель упала, черновик и
    # смена текущего документа откатываются: иначе повтор той же просьбы
    # оставлял бы в архиве пустые копии.
    savepoint = None
    try:
        intent, slug = await _route(llm, text, active, templates)
        if intent == "question" and active is not None:
            answer = await answer_question(
                session, user_id=user_id, document_id=active.id, question=text, llm=llm
            )
            return ChatReply(_esc(answer), _document_buttons(active))

        if intent == "new" or active is None:
            template = next((t for t in templates if t.slug == slug), None)
            if template is None:
                # «Новый документ» без вида: прежний больше не текущий, иначе следующее
                # сообщение с данными дописало бы их в старый документ.
                await chat.set_active_document(user_id, None)
                return ChatReply(ASK_TEMPLATE_TEXT, _template_buttons(templates))
            savepoint = await session.begin_nested()
            started = await _start_document(session, user_id, template.id, text)
            active = started.document

        result = await fill_from_message(
            session, user_id=user_id, document_id=active.id, message=text, llm=llm
        )
    except (LLMError, AppError) as exc:
        if savepoint is not None and savepoint.is_active:
            await savepoint.rollback()
        if isinstance(exc, AppError):
            return ChatReply(_failure_text(exc))
        # Сбой маршрутизации — та же временная недоступность, что и у заполнения.
        # Пользователь видит общую фразу, поэтому причина нужна в логе.
        biz_warn(logger, "agent.chat.llm_failed", error=str(exc))
        return ChatReply(LLM_DOWN_TEXT)
    text_out = _fill_text(result, seller=started.seller if started else None)
    buttons = _document_buttons(result.document)
    if started is not None and await _has_fresh_pending(chat, user_id):
        # Вложение ждало выбора документа, а человек ответил словами: не теряем
        # его молча, но и не распознаём без спроса — оно могло быть о другом.
        text_out += f"\n\n{MEDIA_OFFER_TEXT}"
        buttons = ((ChatButton(MEDIA_BUTTON, f"doc:media:{result.document.id}"),), *buttons)
    return ChatReply(text_out, buttons)


async def _document_for_caption(
    session: AsyncSession,
    user_id: int,
    caption: str,
    active: DocumentView | None,
    llm: LLMClient,
) -> DocumentView | None:
    """Подпись к фото может назвать документ: «счёт для них» начинает новый, «это
    покупатель» — про текущий. Без подписи фото идёт в текущий документ."""
    templates = await list_templates(session, user_id=user_id)
    intent, slug = await _route(llm, caption, active, templates)
    if active is not None and intent != "new":
        return active
    template = next((t for t in templates if t.slug == slug), None)
    if template is None:
        await ChatStateRepository(session).set_active_document(user_id, None)
        return None
    return (await _start_document(session, user_id, template.id, caption)).document


async def _was_sent(session: AsyncSession, document: DocumentView) -> bool:
    return document.id in await last_sends(session, [document.id])


async def _recognize_into(
    session: AsyncSession,
    *,
    user_id: int,
    document_id: int,
    url: str,
    caption: str,
    deps: ChatActionDeps,
) -> ChatReply:
    data = await deps.download(url)
    result = await fill_from_file(
        session,
        user_id=user_id,
        document_id=document_id,
        data=data,
        llm=deps.llm,
        max_bytes=deps.files.media_max_bytes,
        request=caption,
    )
    return ChatReply(_fill_text(result, source="Во вложении"), _document_buttons(result.document))


async def _hear(
    session: AsyncSession, *, sender: ChatSender, attachment: ChatAttachment, deps: ChatActionDeps
) -> ChatReply:
    data = await deps.download(attachment.url)
    transcript = await transcribe(data=data, llm=deps.llm, max_bytes=deps.files.media_max_bytes)
    reply = await handle_chat_message(session, sender=sender, text=transcript, llm=deps.llm)
    heard = transcript[:TRANSCRIPT_PREVIEW_LENGTH]
    if len(transcript) > TRANSCRIPT_PREVIEW_LENGTH:
        heard += "…"
    return ChatReply(f"🎙 <b>Расслышал:</b> <i>«{_esc(heard)}»</i>\n\n{reply.text}", reply.buttons)


async def handle_chat_attachment(
    session: AsyncSession, *, sender: ChatSender, attachment: ChatAttachment, deps: ChatActionDeps
) -> ChatReply:
    user_id = await _ensure_user(session, sender)
    llm = deps.llm
    if llm is None:
        return ChatReply(DISABLED_TEXT)
    kind = _readable_kind(attachment)
    if kind is None:
        return ChatReply(UNSUPPORTED_FILE_TEXT)
    try:
        if kind in AUDIBLE:
            return await _hear(session, sender=sender, attachment=attachment, deps=deps)
        caption = (attachment.caption or "").strip()
        active = await _active_document(session, user_id)
        if active is not None and await _was_sent(session, active):
            # Файл уже ушёл в чат — документ закончен. Новое фото скорее к новому
            # документу, и тихо дописывать в отправленный его нельзя.
            active = None
        if caption:
            active = await _document_for_caption(session, user_id, caption, active, llm)
        if active is None:
            await ChatStateRepository(session).set_pending_media(
                user_id,
                {
                    "kind": attachment.kind,
                    "url": attachment.url,
                    "filename": attachment.filename,
                    "caption": caption,
                    "at": datetime.now(UTC).isoformat(),
                },
            )
            templates = await list_templates(session, user_id=user_id)
            return ChatReply(ASK_MEDIA_TEMPLATE_TEXT, _template_buttons(templates))
        return await _recognize_into(
            session,
            user_id=user_id,
            document_id=active.id,
            url=attachment.url,
            caption=caption,
            deps=deps,
        )
    except InboundFileError as exc:
        return ChatReply(_download_error_text(exc, deps.files))
    except LLMError as exc:
        biz_warn(logger, "agent.chat.llm_failed", error=str(exc), kind=attachment.kind)
        return ChatReply(LLM_DOWN_TEXT)
    except AppError as exc:
        return ChatReply(_failure_text(exc))


def _is_fresh(pending: dict[str, object]) -> bool:
    try:
        at = datetime.fromisoformat(str(pending.get("at")))
    except ValueError:
        return False
    return datetime.now(UTC) - at <= PENDING_MEDIA_TTL


async def _has_fresh_pending(chat: ChatStateRepository, user_id: int) -> bool:
    pending = await chat.pending_media(user_id)
    return pending is not None and _is_fresh(pending)


async def _take_pending(
    chat: ChatStateRepository, user_id: int
) -> tuple[dict[str, object] | None, bool]:
    """Отложенное вложение и признак «было, но устарело»: о протухшем фото
    человеку надо сказать, а не делать вид, что его не присылали."""
    pending = await chat.take_pending_media(user_id)
    if pending is None:
        return None, False
    if not _is_fresh(pending):
        return None, True
    return pending, False


async def _new_from_button(
    session: AsyncSession, *, user_id: int, slug: str, deps: ChatActionDeps
) -> ChatReply:
    chat = ChatStateRepository(session)
    templates = await list_templates(session, user_id=user_id, slug=slug)
    if not templates:
        return ChatReply(UNKNOWN_BUTTON_TEXT)
    document = (await _start_document(session, user_id, templates[0].id)).document
    started = f"{_title_line(document)} — новый документ"
    pending, expired = await _take_pending(chat, user_id)
    if pending is not None and deps.llm is not None:
        try:
            return await _recognize_into(
                session,
                user_id=user_id,
                document_id=document.id,
                url=str(pending["url"]),
                caption=str(pending.get("caption") or ""),
                deps=deps,
            )
        except InboundFileError as exc:
            return ChatReply(
                f"{started}\n\n{_download_error_text(exc, deps.files)}",
                _document_buttons(document),
            )
        except AppError as exc:
            return ChatReply(f"{started}\n\n{_failure_text(exc)}", _document_buttons(document))
    blocks = [started]
    if expired:
        blocks.append(MEDIA_EXPIRED_TEXT)
    if document.missing:
        blocks += [_missing_block(document, "Нужно заполнить"), HOW_TO_FILL_TEXT]
    return ChatReply("\n\n".join(blocks), _document_buttons(document))


def _parse_id(raw: str) -> int | None:
    """id из строки кнопки: строка не доверенная, а BIGINT в базе — 18 цифр."""
    return int(raw) if raw.isdigit() and len(raw) <= 18 else None


async def _buttons_after_failure(
    session: AsyncSession, user_id: int, document_id: int | None, exc: AppError
) -> tuple[tuple[ChatButton, ...], ...]:
    """Кнопки к ошибке: бот уже снял их с нажатого сообщения, и без них человек
    остался бы с текстом ошибки и пустым чатом."""
    new = (ChatButton(NEW_BUTTON, "doc:new"),)
    if document_id is None:
        return (new,)
    if exc.code == "render.pdf_unavailable":
        return ((ChatButton(SEND_DOCX_BUTTON, f"doc:send:{document_id}:docx"),), new)
    try:
        document = await get_document(session, user_id=user_id, document_id=document_id)
    except NotFoundError:
        return (new,)
    return _document_buttons(document)


async def handle_chat_action(
    session: AsyncSession,
    *,
    sender: ChatSender,
    payload: str,
    deps: ChatActionDeps,
) -> ChatReply:
    user_id = await _ensure_user(session, sender)
    chat = ChatStateRepository(session)
    parts = payload.split(":")
    if len(parts) < 2 or parts[0] != "doc":
        return ChatReply(UNKNOWN_BUTTON_TEXT)
    action, args = parts[1], parts[2:]
    document_id = _parse_id(args[0]) if args else None
    try:
        if action == "new" and not args:
            await chat.set_active_document(user_id, None)
            await chat.set_pending_media(user_id, None)
            return ChatReply(
                ASK_TEMPLATE_TEXT, _template_buttons(await list_templates(session, user_id=user_id))
            )

        if action == "new" and len(args) == 1:
            return await _new_from_button(session, user_id=user_id, slug=args[0], deps=deps)

        if action == "confirm" and len(args) == 1 and document_id is not None:
            document = await confirm_fields(session, user_id=user_id, document_id=document_id)
            await chat.set_active_document(user_id, document.id)
            return ChatReply(_confirm_text(document), _document_buttons(document))

        if action == "send" and len(args) == 2 and document_id is not None:
            file, _ = await send_document_to_chat(
                session,
                user_id=user_id,
                max_user_id=sender.max_user_id,
                document_id=document_id,
                fmt=args[1],
                cfg=deps.files,
                bus=deps.bus,
                tokens=deps.tokens,
            )
            return ChatReply(
                f"⏳ Собираю «{_esc(file.filename)}» — пришлю следующим сообщением.",
                (
                    (
                        ChatButton(COPY_BUTTON, f"doc:copy:{args[0]}"),
                        ChatButton(NEW_BUTTON, "doc:new"),
                    ),
                ),
            )

        if action == "copy" and len(args) == 1 and document_id is not None:
            document = await copy_document(session, user_id=user_id, document_id=document_id)
            await chat.set_active_document(user_id, document.id)
            rest = (
                _missing_block(document, "Осталось заполнить")
                if document.missing
                else "👉 Проверьте значения."
            )
            return ChatReply(
                f"📑 <b>Взял за основу «{_esc(document.title)}»</b>\n"
                f"Стороны и условия те же, реквизиты — свежие из карточек.\n\n{rest}",
                _document_buttons(document),
            )

        if action == "media" and len(args) == 1 and document_id is not None:
            document = await get_document(session, user_id=user_id, document_id=document_id)
            pending, _expired = await _take_pending(chat, user_id)
            if pending is None or deps.llm is None:
                return ChatReply(MEDIA_EXPIRED_TEXT, _document_buttons(document))
            await chat.set_active_document(user_id, document.id)
            return await _recognize_into(
                session,
                user_id=user_id,
                document_id=document.id,
                url=str(pending["url"]),
                caption=str(pending.get("caption") or ""),
                deps=deps,
            )
    except InboundFileError as exc:
        return ChatReply(_download_error_text(exc, deps.files))
    except LLMError as exc:
        biz_warn(logger, "agent.chat.llm_failed", error=str(exc), action=action)
        return ChatReply(LLM_DOWN_TEXT)
    except AppError as exc:
        buttons = await _buttons_after_failure(session, user_id, document_id, exc)
        return ChatReply(_failure_text(exc), buttons)
    return ChatReply(UNKNOWN_BUTTON_TEXT)
