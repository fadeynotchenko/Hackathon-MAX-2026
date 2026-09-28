"""Чат: «Изменить этот файл» — документ по присланному файлу, правка сообщением,
готовый файл в оформлении присланного."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from core.events import BOT_ATTACHMENT, BOT_CALLBACK, BOT_MESSAGE, BotCallback
from core.files import FilesConfig, docx_lines
from core.usecases.agent.chat import ASK_FILE_TEXT, EDIT_FILE_BUTTON, EDIT_FILE_OFFER_TEXT
from core.usecases.documents import ensure_builtin_templates
from tests.api.test_chat_dialog import (
    RECOGNIZED,
    USER,
    FakeStorage,
    _attachment,
    _event,
    _message,
    _replies,
)
from tests.api.test_chat_edge_cases import _active
from tests.api.test_events_worker import _handlers
from tests.fakes import FakeLLM
from tests.samples import OFFER_PLACES, offer_docx

PLACES = OFFER_PLACES


def _press(payload: str, event_id: str):
    return _event(
        BOT_CALLBACK,
        BotCallback(max_user_id=USER, chat_id=1, payload=payload).model_dump(),
        event_id,
    )


async def test_file_is_edited_by_message_and_keeps_its_look(
    db: None, session: AsyncSession, redis, tmp_path: Path
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            PLACES,
            {"intent": "fill", "template": ""},
            {"client_name": "ООО «Бета»"},
        ]
    )
    storage = FakeStorage(offer_docx())
    files = FilesConfig(tmp_path / "documents", "soffice", 5)
    handlers = _handlers(redis, llm=llm, fetch=storage, files=files)

    await handlers[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment("file", filename="КП Альфе.docx"), "evt-f")
    )
    (ask,) = await _replies(redis)
    assert ask.text == ASK_FILE_TEXT
    assert ask.buttons is not None and ask.buttons[0][0].text == EDIT_FILE_BUTTON
    assert storage.urls == [], "пока человек не выбрал, файл не качаем"

    await handlers[BOT_CALLBACK](_press("doc:file", "evt-e"))
    found = (await _replies(redis))[-1]
    assert "— по вашему файлу" in found.text
    assert "• Название клиента: <b>ООО «Альфа»</b>" in found.text
    assert "• Сумма: <b>180 000,00</b>" in found.text
    assert "Напишите, что поменять" in found.text
    document_id = await _active(session)
    assert document_id is not None

    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Клиент — ООО Бета"), "evt-m"))
    fixed = (await _replies(redis))[-1]
    assert "• Название клиента: <b>ООО «Бета»</b>" in fixed.text
    await handlers[BOT_CALLBACK](_press(f"doc:confirm:{document_id}", "evt-ok"))
    await handlers[BOT_CALLBACK](_press(f"doc:send:{document_id}:docx", "evt-s"))

    (built,) = (tmp_path / "documents").rglob("*.docx")
    text = docx_lines(built.read_bytes())
    assert "Для: ООО «Бета»" in text, "значение встало на место старого"
    assert "Работы: монтаж оборудования" in text, "остальной текст файла не тронут"
    assert "ООО «Мастер» · ИНН 7707083893" in text, "шапка файла осталась"


async def test_file_for_active_document_can_still_be_edited_itself(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[
            {"intent": "new", "template": "invoice"},
            {"total": "5 000"},
            RECOGNIZED,
            PLACES,
        ]
    )
    storage = FakeStorage(offer_docx())
    handlers = _handlers(redis, llm=llm, fetch=storage)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 5000"), "evt-1"))
    invoice_id = await _active(session)

    await handlers[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment("file", filename="карточка.docx"), "evt-2")
    )
    recognized = (await _replies(redis))[-1]
    assert "• ИНН клиента: <b>7707083893</b>" in recognized.text, "как раньше — в текущий счёт"
    assert EDIT_FILE_OFFER_TEXT in recognized.text
    assert recognized.buttons is not None and recognized.buttons[0][0].payload == "doc:file"

    await handlers[BOT_CALLBACK](_press("doc:file", "evt-3"))
    edited = (await _replies(redis))[-1]
    assert "— по вашему файлу" in edited.text
    assert await _active(session) not in (None, invoice_id)
    assert storage.urls == ["https://i.max.test/p/1"] * 2


async def test_used_file_is_not_offered_to_a_new_document(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    await session.commit()
    llm = FakeLLM(
        json_replies=[{"intent": "new", "template": "invoice"}, {"total": "5 000"}, RECOGNIZED]
    )
    storage = FakeStorage(offer_docx())
    handlers = _handlers(redis, llm=llm, fetch=storage)
    await handlers[BOT_MESSAGE](_event(BOT_MESSAGE, _message("Счёт на 5000"), "evt-1"))
    await handlers[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment("file", filename="карточка.docx"), "evt-2")
    )

    await handlers[BOT_CALLBACK](_press("doc:new:offer", "evt-3"))
    started = (await _replies(redis))[-1]
    assert started.text.startswith("💼 <b>Коммерческое предложение</b> — новый документ")
    assert storage.urls == ["https://i.max.test/p/1"], "разобранный файл второй раз не читаем"
