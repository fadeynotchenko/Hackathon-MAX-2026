"""Диалог с помощником через стрим бота: сообщение → маршрут → документ → ответ с кнопками."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import ChatStateRepository, UserRepository
from core.events import (
    BOT_ATTACHMENT,
    BOT_CALLBACK,
    BOT_MESSAGE,
    BotAttachment,
    BotCallback,
    BotMessage,
    Event,
    NotifyUser,
)
from core.files import FilesConfig, InboundFileError, InboundFileTooLargeError
from core.usecases.agent.chat import (
    ASK_MEDIA_TEMPLATE_TEXT,
    DISABLED_TEXT,
    DOWNLOAD_FAILED_TEXT,
    UNKNOWN_BUTTON_TEXT,
    UNSUPPORTED_FILE_TEXT,
)
from core.usecases.documents import ensure_builtin_templates
from tests.api.test_events_worker import _handlers
from tests.fakes import FakeLLM

USER = 9001


def _event(event_type: str, payload: dict, event_id: str = "evt-1") -> Event:
    return Event(type=event_type, payload=payload, source="bot", id=event_id)


async def _replies(redis) -> list[NotifyUser]:
    """Ответы пользователю; события document.ready в том же стриме пропускаются."""
    entries = await redis.xrange("test:to_bot")
    return [
        NotifyUser.model_validate_json(fields["payload"])
        for _, fields in entries
        if fields["type"] == "notify.user"
    ]


def _message(text: str) -> dict:
    return BotMessage(max_user_id=USER, chat_id=1, text=text, first_name="Фадей").model_dump()


async def test_message_creates_document_and_asks_for_confirmation(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {"total": "120 000", "client_name": "ООО «Ромашка»"},
        ]
    )
    handlers = _handlers(redis, llm=llm)

    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 120 000 для ООО Ромашка")))

    (reply,) = await _replies(redis)
    assert reply.max_user_id == USER
    assert reply.text.startswith("Счёт на оплату")
    assert "— Сумма к оплате: 120 000,00" in reply.text
    labels = [[b.text for b in row] for row in reply.buttons or []]
    assert labels == [["Всё верно"], ["Новый документ"]]

    user = await UserRepository(session).get_by_max_id(USER)
    assert user is not None and user.first_seen_via == "bot"
    assert await ChatStateRepository(session).active_document_id(user.id) is not None
    route_schema = llm.calls[0][2]
    assert route_schema is not None and "invoice" in route_schema["properties"]["template"]["enum"]


async def test_redelivered_message_is_answered_once(db: None, session: AsyncSession, redis) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(json_replies=[{"intent": "new", "template": "offer"}, {"total": "10 000"}])
    handlers = _handlers(redis, llm=llm)
    event = _event(BOT_MESSAGE, _message("КП на 10 000"), event_id="evt-dup")

    await handlers[BOT_MESSAGE](event)
    await handlers[BOT_MESSAGE](event)

    assert len(await _replies(redis)) == 1, "повторная доставка не даёт второго ответа"
    assert len(llm.calls) == 2, "и не зовёт модель повторно"


async def test_unclear_request_offers_template_buttons(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    handlers = _handlers(redis, llm=FakeLLM(json_reply={"intent": "new", "template": ""}))

    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Помоги с бумагами")))

    (reply,) = await _replies(redis)
    payloads = {row[0].payload for row in reply.buttons or []}
    assert payloads == {"doc:new:invoice", "doc:new:offer", "doc:new:service-contract"}


async def test_question_about_active_document_is_answered(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        text="Не хватает номера и даты счёта.",
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {"total": "5 000"},
            {"intent": "question", "template": ""},
        ],
    )
    handlers = _handlers(redis, llm=llm)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 5000"), "evt-a"))
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Чего ещё не хватает?"), "evt-b"))

    replies = await _replies(redis)
    assert replies[-1].text == "Не хватает номера и даты счёта."


async def test_confirm_button_and_unknown_button(
    db: None, session: AsyncSession, redis, tmp_path
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(json_replies=[{"intent": "new", "template": "invoice"}, {"total": "120 000"}])
    files = FilesConfig(tmp_path / "documents", "soffice", 5)
    handlers = _handlers(redis, llm=llm, files=files)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 120 000"), "evt-m"))
    confirm_payload = (await _replies(redis))[0].buttons[0][0].payload  # type: ignore[index]

    await handlers[BOT_CALLBACK](
        _event(
            BOT_CALLBACK,
            BotCallback(max_user_id=USER, chat_id=1, payload=confirm_payload).model_dump(),
            "evt-c",
        )
    )
    await handlers[BOT_CALLBACK](
        _event(
            BOT_CALLBACK,
            BotCallback(max_user_id=USER, chat_id=1, payload="doc:send:99999:docx").model_dump(),
            "evt-x",
        )
    )
    await handlers[BOT_CALLBACK](
        _event(
            BOT_CALLBACK,
            BotCallback(max_user_id=USER, chat_id=1, payload="garbage").model_dump(),
            "evt-g",
        )
    )

    confirmed, foreign, unknown = (await _replies(redis))[1:]
    assert confirmed.text.startswith("Подтвердил. Ещё нужно:")
    assert foreign.text == "Документ не найден", (
        "чужой или несуществующий документ по кнопке не отдаём"
    )
    assert unknown.text == UNKNOWN_BUTTON_TEXT


async def test_disabled_agent_replies_without_model(db: None, session: AsyncSession, redis) -> None:
    handlers = _handlers(redis, llm=None)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт")))
    (reply,) = await _replies(redis)
    assert reply.text == DISABLED_TEXT and reply.buttons is None


def test_reply_payload_round_trips_through_contract() -> None:
    payload = NotifyUser(max_user_id=1, text="x").model_dump()
    assert json.loads(json.dumps(payload))["buttons"] is None


PHOTO = b"\xff\xd8\xff\xe0" + b"\x00" * 64
VOICE = b"OggS\x00\x02" + b"\x00" * 64
RECOGNIZED = {
    "kind": "карточка предприятия",
    "values": [
        {
            "key": "client_name",
            "value": "ООО «Ромашка»",
            "fragment": "ООО «Ромашка»",
            "confidence": 1,
        },
        {"key": "client_inn", "value": "7707083893", "fragment": "ИНН 7707083893", "confidence": 1},
    ],
}


class FakeStorage:
    """Хранилище MAX: отдаёт байты по ссылке и помнит, что у него просили."""

    def __init__(self, data: bytes = PHOTO, error: Exception | None = None) -> None:
        self.data = data
        self.error = error
        self.urls: list[str] = []

    async def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return self.data


def _attachment(kind: str = "image", **extra) -> dict:
    return BotAttachment(
        max_user_id=USER, chat_id=1, kind=kind, url="https://i.max.test/p/1", **extra
    ).model_dump()


async def test_photo_goes_into_the_active_document(db: None, session: AsyncSession, redis) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[{"intent": "new", "template": "invoice"}, {"total": "120 000"}, RECOGNIZED]
    )
    storage = FakeStorage()
    handlers = _handlers(redis, llm=llm, fetch=storage)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 120 000"), "evt-m"))

    await handlers[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment(text="Это покупатель"), "evt-p")
    )

    reply = (await _replies(redis))[-1]
    assert "Во вложении — карточка предприятия." in reply.text
    assert "— ИНН клиента: 7707083893" in reply.text
    assert reply.buttons is not None and reply.buttons[0][0].text == "Всё верно"
    assert storage.urls == ["https://i.max.test/p/1"]
    (photo,) = llm.calls[-1][1][1].attachments
    assert photo.media_type == "image/jpeg"
    assert llm.calls[-1][1][1].content == "Это покупатель"


async def test_photo_without_document_waits_for_the_template_button(
    db: None, session: AsyncSession, redis, tmp_path
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(json_replies=[RECOGNIZED])
    storage = FakeStorage()
    handlers = _handlers(
        redis, llm=llm, fetch=storage, files=FilesConfig(tmp_path / "documents", "soffice", 5)
    )

    await handlers[BOT_ATTACHMENT](_event(BOT_ATTACHMENT, _attachment(), "evt-p"))
    (ask,) = await _replies(redis)
    assert ask.text == ASK_MEDIA_TEMPLATE_TEXT
    assert storage.urls == [], "пока документ не выбран, файл не качаем"

    await handlers[BOT_CALLBACK](
        _event(
            BOT_CALLBACK,
            BotCallback(max_user_id=USER, chat_id=1, payload="doc:new:invoice").model_dump(),
            "evt-c",
        )
    )
    filled = (await _replies(redis))[-1]
    assert filled.text.startswith("Счёт на оплату")
    assert "— Название клиента: ООО «Ромашка»" in filled.text
    assert storage.urls == ["https://i.max.test/p/1"]

    await handlers[BOT_CALLBACK](
        _event(
            BOT_CALLBACK,
            BotCallback(max_user_id=USER, chat_id=1, payload="doc:new:offer").model_dump(),
            "evt-c2",
        )
    )
    second = (await _replies(redis))[-1]
    assert second.text.startswith("Начал «Коммерческое предложение».")
    assert len(storage.urls) == 1, "отложенное фото распознаётся один раз"


async def test_caption_names_the_document_for_the_photo(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(json_replies=[{"intent": "new", "template": "service-contract"}, RECOGNIZED])
    handlers = _handlers(redis, llm=llm, fetch=FakeStorage())

    await handlers[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment(text="Договор с ними"), "evt-p")
    )

    (reply,) = await _replies(redis)
    assert reply.text.startswith("Договор оказания услуг")
    assert "— ИНН клиента: 7707083893" in reply.text


async def test_voice_is_transcribed_and_handled_as_text(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"text": "Счёт на 120 000 для ООО Ромашка"},
            {"intent": "new", "template": "invoice"},
            {"total": "120 000", "client_name": "ООО «Ромашка»"},
        ]
    )
    storage = FakeStorage(VOICE)
    handlers = _handlers(redis, llm=llm, fetch=storage)

    await handlers[BOT_ATTACHMENT](_event(BOT_ATTACHMENT, _attachment("audio"), "evt-v"))

    (reply,) = await _replies(redis)
    assert reply.text.startswith("Расслышал: «Счёт на 120 000 для ООО Ромашка»")
    assert "— Сумма к оплате: 120\u00a0000,00" in reply.text
    assert llm.calls[1][1][1].content == "Счёт на 120 000 для ООО Ромашка"


async def test_attachment_problems_are_explained(db: None, session: AsyncSession, redis) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    broken = FakeStorage(error=InboundFileError("410"))
    handlers = _handlers(redis, llm=FakeLLM(), fetch=broken)

    await handlers[BOT_ATTACHMENT](_event(BOT_ATTACHMENT, _attachment("audio"), "evt-1"))
    await handlers[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment("file", filename="прайс.xlsx"), "evt-2")
    )
    await handlers[BOT_ATTACHMENT](
        _event(
            BOT_ATTACHMENT,
            _attachment("file", filename="scan.pdf"),
            "evt-3",
        )
    )
    oversized = FakeStorage(error=InboundFileTooLargeError("big"))
    await _handlers(redis, llm=FakeLLM(), fetch=oversized)[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment("audio"), "evt-4")
    )

    download, unsupported, pending, large = await _replies(redis)
    assert download.text == DOWNLOAD_FAILED_TEXT
    assert unsupported.text == UNSUPPORTED_FILE_TEXT
    assert pending.text == ASK_MEDIA_TEMPLATE_TEXT
    assert large.text.startswith("Файл больше 10 МБ")
    assert broken.urls == ["https://i.max.test/p/1"], "xlsx даже не скачивали"


async def test_attachment_without_agent_says_it_is_off(
    db: None, session: AsyncSession, redis
) -> None:
    storage = FakeStorage()
    await _handlers(redis, llm=None, fetch=storage)[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment(), "evt-x")
    )
    (reply,) = await _replies(redis)
    assert reply.text == DISABLED_TEXT and storage.urls == []


def test_attachment_contract_accepts_only_https_links() -> None:
    with pytest.raises(ValidationError):
        BotAttachment(max_user_id=1, chat_id=1, kind="image", url="http://i.max.test/p")
    with pytest.raises(ValidationError):
        BotAttachment(max_user_id=1, chat_id=1, kind="video", url="https://i.max.test/p")


async def test_sent_document_can_be_taken_as_a_base(
    db: None, session: AsyncSession, redis, tmp_path
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"intent": "new", "template": "offer"},
            {
                "date": "24.09.2026",
                "seller_name": "ООО «Ромашка»",
                "client_name": "ООО «Клиент»",
                "subject": "Сайт",
                "scope": "Вёрстка",
                "total": "90 000",
                "valid_until": "31.10.2026",
            },
        ]
    )
    handlers = _handlers(redis, llm=llm, files=FilesConfig(tmp_path / "documents", "soffice", 5))
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("КП на сайт"), "evt-1"))
    confirm = (await _replies(redis))[0].buttons[0][0].payload  # type: ignore[index]
    await handlers[BOT_CALLBACK](
        _event(
            BOT_CALLBACK,
            BotCallback(max_user_id=USER, chat_id=1, payload=confirm).model_dump(),
            "evt-2",
        )
    )
    send = (await _replies(redis))[1].buttons[0][0].payload  # type: ignore[index]
    await handlers[BOT_CALLBACK](
        _event(
            BOT_CALLBACK,
            BotCallback(max_user_id=USER, chat_id=1, payload=send).model_dump(),
            "evt-3",
        )
    )
    sending = next(reply for reply in await _replies(redis) if "Собираю" in reply.text)
    base = sending.buttons[0][0]  # type: ignore[index]
    assert base.text == "На основе этого" and base.payload.startswith("doc:copy:")

    await handlers[BOT_CALLBACK](
        _event(
            BOT_CALLBACK,
            BotCallback(max_user_id=USER, chat_id=1, payload=base.payload).model_dump(),
            "evt-4",
        )
    )
    copied = (await _replies(redis))[-1]
    assert copied.text.startswith("Взял за основу «Коммерческое предложение»")
    assert "Осталось заполнить: Дата предложения, Предложение действует до." in copied.text
