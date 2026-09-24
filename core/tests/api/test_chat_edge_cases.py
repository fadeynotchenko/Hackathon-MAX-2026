"""Граничные случаи диалога в чате: смена документа, отложенное фото, сбои модели и кнопок."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Document
from core.db.repositories import ChatStateRepository, UserRepository
from core.events import BOT_ATTACHMENT, BOT_CALLBACK, BOT_MESSAGE, BotCallback
from core.files import FilesConfig
from core.llm import ChatMessage, LLMUnavailableError
from core.usecases.agent.chat import (
    ASK_MEDIA_TEMPLATE_TEXT,
    ASK_TEMPLATE_TEXT,
    LLM_DOWN_TEXT,
    MEDIA_OFFER_TEXT,
    UNKNOWN_BUTTON_TEXT,
)
from core.usecases.documents import create_organization, ensure_builtin_templates
from tests.api.test_chat_dialog import (
    RECOGNIZED,
    USER,
    FakeStorage,
    _attachment,
    _event,
    _message,
    _replies,
)
from tests.api.test_events_worker import _handlers
from tests.fakes import FakeLLM
from tests.usecases.test_documents import make_user

READY_OFFER = {
    "date": "24.09.2026",
    "seller_name": "ООО «Ромашка»",
    "client_name": "ООО «Клиент»",
    "subject": "Сайт",
    "scope": "Вёрстка",
    "total": "90 000",
    "valid_until": "31.10.2026",
}
# Значения берутся только из слов человека: в сообщении должно быть всё, что в READY_OFFER.
OFFER_TEXT = "КП от ООО Ромашка для ООО Клиент на сайт: вёрстка, 90 000, действует до 31.10.2026"


class FlakyLLM(FakeLLM):
    """Маршрут отвечает, а заполнение падает: модель отвалилась посреди просьбы."""

    def __init__(self, *, ok_calls: int, **kw: Any) -> None:
        super().__init__(**kw)
        self.ok_calls = ok_calls

    async def complete_json(
        self, messages: Sequence[ChatMessage], *, schema: Mapping[str, Any]
    ) -> dict[str, Any]:
        if len(self.calls) >= self.ok_calls:
            self.calls.append(("json", list(messages), schema))
            raise LLMUnavailableError("fake: отвалилась")
        return await super().complete_json(messages, schema=schema)


def _press(payload: str, event_id: str) -> tuple[str, Any]:
    return BOT_CALLBACK, _event(
        BOT_CALLBACK,
        BotCallback(max_user_id=USER, chat_id=1, payload=payload).model_dump(),
        event_id,
    )


async def _documents(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Document))).scalar_one()


async def _active(session: AsyncSession) -> int | None:
    user = await UserRepository(session).get_by_max_id(USER)
    assert user is not None
    return await ChatStateRepository(session).active_document_id(user.id)


async def test_new_document_in_words_forgets_the_previous_one(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {"total": "5 000"},
            {"intent": "new", "template": ""},
        ]
    )
    handlers = _handlers(redis, llm=llm)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 5000"), "evt-1"))
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Новый документ"), "evt-2"))

    reply = (await _replies(redis))[-1]
    assert reply.text == ASK_TEMPLATE_TEXT
    assert await _active(session) is None, "следующие данные не допишутся в старый счёт"


async def test_model_failure_leaves_no_empty_draft(db: None, session: AsyncSession, redis) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FlakyLLM(ok_calls=1, json_replies=[{"intent": "new", "template": "invoice"}])
    handlers = _handlers(redis, llm=llm)

    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 5000"), "evt-1"))

    (reply,) = await _replies(redis)
    assert reply.text == LLM_DOWN_TEXT
    assert await _documents(session) == 0, "повтор просьбы не оставит в архиве пустых копий"
    assert await _active(session) is None


async def test_photo_after_sending_asks_which_document(
    db: None, session: AsyncSession, redis, tmp_path
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(json_replies=[{"intent": "new", "template": "offer"}, READY_OFFER])
    storage = FakeStorage()
    files = FilesConfig(tmp_path / "documents", "soffice", 5)
    handlers = _handlers(redis, llm=llm, fetch=storage, files=files)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message(OFFER_TEXT), "evt-1"))
    confirm = (await _replies(redis))[0].buttons[0][0].payload  # type: ignore[index]
    await handlers[BOT_CALLBACK](_press(confirm, "evt-2")[1])
    await handlers[BOT_CALLBACK](_press(f"doc:send:{confirm.split(':')[2]}:docx", "evt-3")[1])

    await handlers[BOT_ATTACHMENT](_event(BOT_ATTACHMENT, _attachment(), "evt-4"))

    reply = (await _replies(redis))[-1]
    assert reply.text == ASK_MEDIA_TEMPLATE_TEXT, "отправленный документ фото не меняет"
    assert storage.urls == []


async def test_caption_asking_for_new_document_is_not_put_into_the_active_one(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {"total": "5 000"},
            {"intent": "new", "template": "service-contract"},
            RECOGNIZED,
        ]
    )
    handlers = _handlers(redis, llm=llm, fetch=FakeStorage())
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 5000"), "evt-1"))
    invoice_id = await _active(session)

    await handlers[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment(text="Новый договор с ними"), "evt-2")
    )

    reply = (await _replies(redis))[-1]
    assert reply.text.startswith("Договор оказания услуг")
    assert await _active(session) != invoice_id


async def test_words_answer_to_pending_photo_offers_to_use_it(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(json_replies=[{"intent": "new", "template": "invoice"}, {}, RECOGNIZED])
    storage = FakeStorage()
    handlers = _handlers(redis, llm=llm, fetch=storage)
    await handlers[BOT_ATTACHMENT](_event(BOT_ATTACHMENT, _attachment(), "evt-1"))

    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("счёт"), "evt-2"))
    offer = (await _replies(redis))[-1]
    assert MEDIA_OFFER_TEXT in offer.text
    use = offer.buttons[0][0]  # type: ignore[index]
    assert use.text == "Взять из вложения" and use.payload.startswith("doc:media:")
    assert storage.urls == [], "без спроса вложение не распознаётся"

    await handlers[BOT_CALLBACK](_press(use.payload, "evt-3")[1])
    filled = (await _replies(redis))[-1]
    assert "— Название клиента: ООО «Ромашка»" in filled.text
    assert storage.urls == ["https://i.max.test/p/1"]


async def test_failed_buttons_come_back_with_buttons(
    db: None, session: AsyncSession, redis, tmp_path
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(json_replies=[{"intent": "new", "template": "offer"}, READY_OFFER])
    files = FilesConfig(tmp_path / "documents", str(tmp_path / "no-soffice"), 5)
    handlers = _handlers(redis, llm=llm, files=files)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message(OFFER_TEXT), "evt-1"))
    confirm = (await _replies(redis))[0].buttons[0][0].payload  # type: ignore[index]
    document_id = confirm.split(":")[2]
    await handlers[BOT_CALLBACK](_press(confirm, "evt-2")[1])

    await handlers[BOT_CALLBACK](_press(f"doc:send:{document_id}:pdf", "evt-3")[1])
    pdf = (await _replies(redis))[-1]
    assert pdf.text.startswith("PDF сейчас собрать нечем")
    assert pdf.buttons is not None
    assert pdf.buttons[0][0].payload == f"doc:send:{document_id}:docx"

    await handlers[BOT_CALLBACK](_press("doc:confirm:424242", "evt-4")[1])
    missing = (await _replies(redis))[-1]
    assert missing.text == "Документ не найден"
    assert [[b.payload for b in row] for row in missing.buttons or []] == [["doc:new"]]

    await handlers[BOT_CALLBACK](_press("doc:confirm:" + "9" * 30, "evt-5")[1])
    assert (await _replies(redis))[-1].text == UNKNOWN_BUTTON_TEXT, "мусорный id — не 500"


async def test_confirm_explains_errors_when_nothing_is_missing(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    user_id = await make_user(session, max_user_id=USER)
    await create_organization(
        session,
        user_id=user_id,
        name="ООО «Ромашка»",
        values={
            "inn": "7707083893",
            "bank": "ПАО Сбербанк",
            "bic": "044525225",
            "account": "40702810438000123459",
        },
    )
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {
                "number": "1",
                "client_name": "ООО «Клиент»",
                "item": "Сайт",
                "total": "5 000",
                "seller_bic": "044525974",
            },
        ]
    )
    handlers = _handlers(redis, llm=llm)
    text = "Счёт № 1 для ООО Клиент за сайт на 5 000, БИК 044525974"
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message(text), "evt-1"))
    filled = (await _replies(redis))[-1]
    assert "Проверьте: «Расчётный счёт»: счёт не сходится с БИК банка." in filled.text

    confirm = filled.buttons[0][0].payload  # type: ignore[index]
    await handlers[BOT_CALLBACK](_press(confirm, "evt-2")[1])
    confirmed = (await _replies(redis))[-1]
    assert confirmed.text.startswith("Подтвердил, но есть ошибки: «Расчётный счёт»")
    assert "Ещё нужно: ." not in confirmed.text


async def test_seller_is_named_when_there_are_several_organizations(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    user_id = await make_user(session, max_user_id=USER)
    await create_organization(session, user_id=user_id, name="ИП Иванов", values={})
    await create_organization(session, user_id=user_id, name="ООО «Ромашка»", values={})
    await session.commit()
    llm = FakeLLM(json_replies=[{"intent": "new", "template": "invoice"}, {}])
    handlers = _handlers(redis, llm=llm)

    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт от Ромашки"), "evt-1"))

    assert "От: ООО «Ромашка»" in (await _replies(redis))[-1].text


async def test_empty_model_answer_is_not_silence(db: None, session: AsyncSession, redis) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        text="   ",
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {"total": "5 000"},
            {"intent": "question", "template": ""},
        ],
    )
    handlers = _handlers(redis, llm=llm)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 5000"), "evt-1"))
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Что ещё нужно?"), "evt-2"))

    replies = await _replies(redis)
    assert len(replies) == 2
    assert replies[-1].text == "Помощник не нашёл, что ответить. Спросите по-другому"


async def test_double_tap_on_a_button_is_handled_once(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    handlers = _handlers(redis, llm=FakeLLM())

    await handlers[BOT_CALLBACK](_press("doc:new", "evt-tap-1")[1])
    await handlers[BOT_CALLBACK](_press("doc:new", "evt-tap-2")[1])

    assert len(await _replies(redis)) == 1, "второе нажатие той же кнопки — дубль"


async def test_event_left_in_progress_by_a_dead_process_is_retried_not_dropped(
    db: None, session: AsyncSession, redis
) -> None:
    import pytest

    from core.api.events_worker import PROCESSED_KEY, EventInProgressError

    await ensure_builtin_templates(session)
    await session.commit()
    handlers = _handlers(redis, llm=FakeLLM(json_reply={"intent": "new", "template": ""}))
    event = _event(BOT_MESSAGE, _message("Помоги"), "evt-crashed")
    await redis.set(f"{PROCESSED_KEY}evt-crashed", "working", ex=60)

    with pytest.raises(EventInProgressError):
        await handlers[BOT_MESSAGE](event)
    assert await _replies(redis) == [], "пока отметка жива — не отвечаем и не подтверждаем"

    await redis.delete(f"{PROCESSED_KEY}evt-crashed")
    await handlers[BOT_MESSAGE](event)
    await handlers[BOT_MESSAGE](event)
    assert len(await _replies(redis)) == 1, "после истечения отметки — ровно один ответ"


async def test_repeating_the_same_value_says_nothing_changed(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {"total": "120 000"},
            {"intent": "fill", "template": ""},
            {"total": "120000"},
        ]
    )
    handlers = _handlers(redis, llm=llm)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 120 000"), "evt-1"))
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Сумма 120000"), "evt-2"))

    reply = (await _replies(redis))[-1]
    assert "Ничего не поменял — в документе уже так: сумма к оплате." in reply.text
    assert "не нашёл значений" not in reply.text


async def test_rejected_edit_is_not_reported_as_written(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {"total": "120 000"},
            {"intent": "fill", "template": ""},
            {"total": "сто пятьдесят"},
        ]
    )
    handlers = _handlers(redis, llm=llm)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 120 000"), "evt-1"))
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("сумма сто пятьдесят"), "evt-2"))

    reply = (await _replies(redis))[-1]
    assert "Не записал: «Сумма к оплате»: не похоже на сумму." in reply.text
    assert "— Сумма к оплате" not in reply.text, "прежняя сумма осталась, но это не запись"
    assert "не нашёл значений" not in reply.text
