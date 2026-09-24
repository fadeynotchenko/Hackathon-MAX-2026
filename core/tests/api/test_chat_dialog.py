"""Диалог с помощником через стрим бота: сообщение → маршрут → документ → ответ с кнопками."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import ChatStateRepository, UserRepository
from core.events import (
    BOT_CALLBACK,
    BOT_MESSAGE,
    BotCallback,
    BotMessage,
    Event,
    NotifyUser,
)
from core.files import FilesConfig
from core.usecases.agent.chat import DISABLED_TEXT, UNKNOWN_BUTTON_TEXT
from core.usecases.documents import ensure_builtin_templates
from tests.api.test_events_worker import _handlers
from tests.fakes import FakeLLM

USER = 9001


def _event(event_type: str, payload: dict, event_id: str = "evt-1") -> Event:
    return Event(type=event_type, payload=payload, source="bot", id=event_id)


async def _replies(redis) -> list[NotifyUser]:
    entries = await redis.xrange("test:to_bot")
    return [NotifyUser.model_validate_json(fields["payload"]) for _, fields in entries]


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
