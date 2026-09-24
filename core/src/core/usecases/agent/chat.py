"""Диалог с помощником в чате бота: сообщение или нажатая кнопка → ответ с кнопками.

Сценарий не знает про MAX и Redis: на вход — кто написал и что, на выход —
текст и кнопки, которые канал доставит сам. Документ, над которым идёт работа,
запоминается в ``chat_states``: пользователь пишет «поменяй срок на 10 дней»,
не называя документ.

Кнопки несут действие строкой ``doc:<действие>[:<id>[:<формат>]]``: нажатие
приходит обратно в ядро, и права проверяются заново — строка из кнопки не
доверенная, документ ищется только среди документов нажавшего.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import (
    ChatStateRepository,
    DownloadTokenRepository,
    UserRepository,
    UserUpsert,
)
from core.domain.documents import render_context
from core.domain.exceptions import AppError, NotFoundError
from core.events import EventBus
from core.files import FilesConfig
from core.llm import ChatMessage, LLMClient, LLMError
from core.usecases.agent.service import AgentFillResult, answer_question, fill_from_message
from core.usecases.documents import (
    DocumentView,
    TemplateView,
    confirm_fields,
    create_draft,
    get_document,
    list_templates,
    send_document_to_chat,
)

DISABLED_TEXT = (
    "Помощник сейчас выключен. Документ можно заполнить в мини-приложении — "
    "кнопка «Открыть приложение»."
)
ASK_TEMPLATE_TEXT = (
    "Какой документ подготовить? Выберите ниже или опишите словами, например: "
    "«Счёт на 120 000 для ООО Ромашка за разработку сайта»."
)
UNKNOWN_BUTTON_TEXT = "Эта кнопка больше не работает. Напишите, что нужно сделать."

ROUTE_INSTRUCTIONS = """Определи, чего хочет пользователь в чате с помощником по документам.
intent:
- new — подготовить новый документ (укажи его вид в template);
- fill — дописать или поправить текущий документ;
- question — вопрос о текущем документе, ничего менять не надо.
Если текущего документа нет, запрос на заполнение означает new.
template — вид нового документа из списка ниже или пустая строка, если вид не ясен."""


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
class ChatActionDeps:
    """Всё, что нужно кнопке «прислать файл»: сборка, событие боту, одноразовый токен."""

    files: FilesConfig
    bus: EventBus
    tokens: DownloadTokenRepository


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


async def _ensure_user(session: AsyncSession, sender: ChatSender) -> int:
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(
            max_user_id=sender.max_user_id,
            first_name=sender.first_name,
            last_name=sender.last_name,
            username=sender.username,
            via="bot",
        ),
        touch_login=False,
        now=datetime.now(UTC),
    )
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
    current = f"{active.template.title} «{active.title}»" if active else "нет"
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
            active = await create_draft(session, user_id=user_id, template_id=template.id)
            await ChatStateRepository(session).set_active_document(user_id, active.id)

        result = await fill_from_message(
            session, user_id=user_id, document_id=active.id, message=text, llm=llm
        )
    except LLMError:
        # Сбой маршрутизации — та же временная недоступность, что и у заполнения.
        return ChatReply("Помощник не отвечает, попробуйте ещё раз чуть позже.")
    except AppError as exc:
        return ChatReply(exc.public_message)
    return ChatReply(_fill_text(result), _document_buttons(result.document))


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
            return ChatReply(
                ASK_TEMPLATE_TEXT, _template_buttons(await list_templates(session, user_id=user_id))
            )

        if action == "new" and len(args) == 1:
            templates = await list_templates(session, user_id=user_id, slug=args[0])
            if not templates:
                return ChatReply(UNKNOWN_BUTTON_TEXT)
            document = await create_draft(session, user_id=user_id, template_id=templates[0].id)
            await chat.set_active_document(user_id, document.id)
            return ChatReply(
                f"Начал «{document.template.title}». Напишите данные одним сообщением: "
                f"{_missing_text(document)}.",
                _document_buttons(document),
            )

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
            return ChatReply(f"Собираю «{file.filename}», пришлю следующим сообщением.")
    except AppError as exc:
        return ChatReply(exc.public_message)
    return ChatReply(UNKNOWN_BUTTON_TEXT)
