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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    stems,
)
from core.usecases.documents import (
    DocumentView,
    OrganizationView,
    TemplateView,
    confirm_fields,
    copy_document,
    create_draft,
    get_document,
    list_organizations,
    list_templates,
    send_document_to_chat,
)
from core.usecases.users import mark_active

DISABLED_TEXT = (
    "Помощник сейчас выключен. Документ можно заполнить в мини-приложении — "
    "кнопка «Открыть приложение»."
)
ASK_TEMPLATE_TEXT = (
    "Какой документ подготовить? Выберите ниже или опишите словами, например: "
    "«Счёт на 120 000 для ООО Ромашка за разработку сайта»."
)
ASK_MEDIA_TEMPLATE_TEXT = (
    "Для какого документа взять данные из вложения? Выберите ниже — распознаю и покажу, что нашёл."
)
UNKNOWN_BUTTON_TEXT = "Эта кнопка больше не работает. Напишите, что нужно сделать."
LLM_DOWN_TEXT = "Помощник не отвечает, попробуйте ещё раз чуть позже."
DOWNLOAD_FAILED_TEXT = "Не получилось скачать вложение из MAX, пришлите его ещё раз."
UNSUPPORTED_FILE_TEXT = "Такой файл не прочитать. Подойдёт фото, PDF, DOCX или голосовое."

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


def _failure_text(exc: AppError) -> str:
    """Текст ошибки для чата. Сбой на нашей стороне или у модели (5xx) пишется в лог:
    в HTTP это делает обработчик ошибок api, а у событий бота его нет."""
    if exc.status_code >= 500:
        biz_warn(logger, "agent.chat.failed", code=exc.code, error=exc.log_message or str(exc))
    return exc.public_message


def _template_buttons(templates: list[TemplateView]) -> tuple[tuple[ChatButton, ...], ...]:
    return tuple((ChatButton(t.title, f"doc:new:{t.slug}"),) for t in templates)


def _document_buttons(document: DocumentView) -> tuple[tuple[ChatButton, ...], ...]:
    rows: list[tuple[ChatButton, ...]] = []
    if document.unconfirmed:
        rows.append((ChatButton("Всё верно", f"doc:confirm:{document.id}"),))
    elif document.ready:
        rows.append(
            (
                ChatButton("Прислать DOCX", f"doc:send:{document.id}:docx"),
                ChatButton("Прислать PDF", f"doc:send:{document.id}:pdf"),
            )
        )
    rows.append((ChatButton("Новый документ", "doc:new"),))
    return tuple(rows)


def _missing_text(document: DocumentView) -> str:
    labels = {spec.key: spec.label for spec in document.template.fields}
    return ", ".join(labels[key] for key in document.missing)


def _fill_text(result: AgentFillResult) -> str:
    """Ответ показывает значения, а не только названия полей: подтверждать
    человек должен то, что увидел, а не то, что помощник пообещал заполнить."""
    document = result.document
    context = render_context(document.template.fields, document.values)
    labels = {spec.key: spec.label for spec in document.template.fields}
    lines = [f"{document.template.title} «{document.title}»", result.reply]
    lines += [f"— {labels[key]}: {context[key]}" for key in result.filled if context.get(key)]
    return "\n".join(lines)


def _download_error_text(exc: InboundFileError, files: FilesConfig) -> str:
    if isinstance(exc, InboundFileTooLargeError):
        return f"Файл больше {files.media_max_bytes // (1024 * 1024)} МБ, пришлите поменьше."
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
        f"{active.template.title} «{active.title}», ждёт значений: {_missing_text(active) or 'нет'}"
        if active
        else "нет"
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


def named_organization(organizations: list[OrganizationView], text: str) -> int | None:
    """Своя организация, названная в сообщении: «счёт от ИП Нотченко». Если названы
    две или ни одной — не угадываем, документ пойдёт от основной."""
    said = stems(text)
    named = [o.id for o in organizations if (stems(o.name) - _LEGAL_FORM_STEMS) & said]
    return named[0] if len(named) == 1 else None


async def _start_document(
    session: AsyncSession, user_id: int, template_id: int, text: str = ""
) -> DocumentView:
    organization_id = None
    if text:
        organizations = await list_organizations(session, user_id=user_id)
        if len(organizations) > 1:
            organization_id = named_organization(organizations, text)
    document = await create_draft(
        session, user_id=user_id, template_id=template_id, organization_id=organization_id
    )
    await ChatStateRepository(session).set_active_document(user_id, document.id)
    return document


async def handle_chat_message(
    session: AsyncSession, *, sender: ChatSender, text: str, llm: LLMClient | None
) -> ChatReply:
    user_id = await _ensure_user(session, sender)
    if llm is None:
        return ChatReply(DISABLED_TEXT)
    templates = await list_templates(session, user_id=user_id)
    active = await _active_document(session, user_id)
    try:
        intent, slug = await _route(llm, text, active, templates)
        if intent == "question" and active is not None:
            answer = await answer_question(
                session, user_id=user_id, document_id=active.id, question=text, llm=llm
            )
            return ChatReply(answer, _document_buttons(active))

        if intent == "new" or active is None:
            template = next((t for t in templates if t.slug == slug), None)
            if template is None:
                return ChatReply(ASK_TEMPLATE_TEXT, _template_buttons(templates))
            active = await _start_document(session, user_id, template.id, text)
            # Документ начат словами: отложенное раньше фото к нему уже не относится.
            await ChatStateRepository(session).set_pending_media(user_id, None)

        result = await fill_from_message(
            session, user_id=user_id, document_id=active.id, message=text, llm=llm
        )
    except LLMError as exc:
        # Сбой маршрутизации — та же временная недоступность, что и у заполнения.
        # Пользователь видит общую фразу, поэтому причина нужна в логе.
        biz_warn(logger, "agent.chat.llm_failed", error=str(exc))
        return ChatReply(LLM_DOWN_TEXT)
    except AppError as exc:
        return ChatReply(_failure_text(exc))
    return ChatReply(_fill_text(result), _document_buttons(result.document))


async def _document_for_caption(
    session: AsyncSession, user_id: int, caption: str, llm: LLMClient
) -> DocumentView | None:
    """Подпись к фото без текущего документа может назвать его вид: «счёт для них»."""
    templates = await list_templates(session, user_id=user_id)
    _intent, slug = await _route(llm, caption, None, templates)
    template = next((t for t in templates if t.slug == slug), None)
    if template is None:
        return None
    return await _start_document(session, user_id, template.id, caption)


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
    return ChatReply(_fill_text(result), _document_buttons(result.document))


async def _hear(
    session: AsyncSession, *, sender: ChatSender, attachment: ChatAttachment, deps: ChatActionDeps
) -> ChatReply:
    data = await deps.download(attachment.url)
    transcript = await transcribe(data=data, llm=deps.llm, max_bytes=deps.files.media_max_bytes)
    reply = await handle_chat_message(session, sender=sender, text=transcript, llm=deps.llm)
    heard = transcript[:TRANSCRIPT_PREVIEW_LENGTH]
    if len(transcript) > TRANSCRIPT_PREVIEW_LENGTH:
        heard += "…"
    return ChatReply(f"Расслышал: «{heard}»\n\n{reply.text}", reply.buttons)


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
        if active is None and caption:
            active = await _document_for_caption(session, user_id, caption, llm)
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


async def _take_fresh_pending(chat: ChatStateRepository, user_id: int) -> dict[str, object] | None:
    pending = await chat.take_pending_media(user_id)
    if pending is None:
        return None
    try:
        at = datetime.fromisoformat(str(pending.get("at")))
    except ValueError:
        return None
    if datetime.now(UTC) - at > PENDING_MEDIA_TTL:
        return None
    return pending


async def _new_from_button(
    session: AsyncSession, *, user_id: int, slug: str, deps: ChatActionDeps
) -> ChatReply:
    chat = ChatStateRepository(session)
    templates = await list_templates(session, user_id=user_id, slug=slug)
    if not templates:
        return ChatReply(UNKNOWN_BUTTON_TEXT)
    document = await _start_document(session, user_id, templates[0].id)
    started = f"Начал «{document.template.title}»."
    pending = await _take_fresh_pending(chat, user_id)
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
                f"{started} {_download_error_text(exc, deps.files)}", _document_buttons(document)
            )
        except AppError as exc:
            return ChatReply(f"{started} {_failure_text(exc)}", _document_buttons(document))
    return ChatReply(
        f"{started} Напишите данные одним сообщением, надиктуйте голосовым или пришлите "
        f"фото карточки: {_missing_text(document)}.",
        _document_buttons(document),
    )


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
    try:
        if action == "new" and not args:
            await chat.set_active_document(user_id, None)
            await chat.set_pending_media(user_id, None)
            return ChatReply(
                ASK_TEMPLATE_TEXT, _template_buttons(await list_templates(session, user_id=user_id))
            )

        if action == "new" and len(args) == 1:
            return await _new_from_button(session, user_id=user_id, slug=args[0], deps=deps)

        if action == "confirm" and len(args) == 1 and args[0].isdigit():
            document = await confirm_fields(session, user_id=user_id, document_id=int(args[0]))
            await chat.set_active_document(user_id, document.id)
            text = (
                "Готово, документ заполнен. Прислать файл?"
                if document.ready
                else f"Подтвердил. Ещё нужно: {_missing_text(document)}."
            )
            return ChatReply(text, _document_buttons(document))

        if action == "send" and len(args) == 2 and args[0].isdigit():
            file, _ = await send_document_to_chat(
                session,
                user_id=user_id,
                max_user_id=sender.max_user_id,
                document_id=int(args[0]),
                fmt=args[1],
                cfg=deps.files,
                bus=deps.bus,
                tokens=deps.tokens,
            )
            return ChatReply(
                f"Собираю «{file.filename}», пришлю следующим сообщением.",
                (
                    (
                        ChatButton("На основе этого", f"doc:copy:{args[0]}"),
                        ChatButton("Новый документ", "doc:new"),
                    ),
                ),
            )

        if action == "copy" and len(args) == 1 and args[0].isdigit():
            document = await copy_document(session, user_id=user_id, document_id=int(args[0]))
            await chat.set_active_document(user_id, document.id)
            rest = (
                f"Осталось заполнить: {_missing_text(document)}."
                if document.missing
                else "Проверьте значения."
            )
            return ChatReply(
                f"Взял за основу «{document.title}»: стороны и условия те же, реквизиты — "
                f"свежие из карточек. {rest}",
                _document_buttons(document),
            )
    except AppError as exc:
        return ChatReply(_failure_text(exc))
    return ChatReply(UNKNOWN_BUTTON_TEXT)
