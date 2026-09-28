"""Чат: свой файл и свои шаблоны — только в мини-приложении.

Присланный DOCX или PDF в чате — источник реквизитов, как фото: бот предлагает
стандартный документ, а не правку самого файла. Кнопка «Изменить этот файл» из
прежних сообщений объясняет, где это теперь делается.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories import UserRepository, UserUpsert
from core.domain.documents import FieldSpec
from core.events import BOT_ATTACHMENT, BOT_CALLBACK, BotCallback
from core.usecases.agent.chat import ASK_MEDIA_TEMPLATE_TEXT, OWN_FILE_IN_APP_TEXT
from core.usecases.documents import TemplateInput, create_template, ensure_builtin_templates
from core.usecases.documents.builtin import BUILTIN_TEMPLATES
from tests.api.test_chat_dialog import USER, FakeStorage, _attachment, _event, _replies
from tests.api.test_events_worker import _handlers
from tests.fakes import FakeLLM
from tests.samples import offer_docx


def _press(payload: str, event_id: str):
    return _event(
        BOT_CALLBACK,
        BotCallback(max_user_id=USER, chat_id=1, payload=payload).model_dump(),
        event_id,
    )


async def test_file_in_chat_offers_standard_documents_only(
    db: None, session: AsyncSession, redis
) -> None:
    await ensure_builtin_templates(session)
    user = await UserRepository(session).upsert_from_max(
        UserUpsert(max_user_id=USER, first_name="Фадей"), touch_login=False, now=datetime.now(UTC)
    )
    await create_template(
        session,
        user_id=user.id,
        data=TemplateInput(
            "Акт", "", "Акт для {{client_name}}", (FieldSpec("client_name", "Клиент"),)
        ),
    )
    await session.commit()
    handlers = _handlers(redis, llm=FakeLLM(), fetch=FakeStorage(offer_docx()))

    await handlers[BOT_ATTACHMENT](
        _event(BOT_ATTACHMENT, _attachment("file", filename="КП Альфе.docx"), "evt-f")
    )
    await handlers[BOT_CALLBACK](_press("doc:file", "evt-e"))

    ask, old_button = await _replies(redis)
    assert ask.text == ASK_MEDIA_TEMPLATE_TEXT
    titles = [button.text for row in ask.buttons or [] for button in row]
    assert len(titles) == len(BUILTIN_TEMPLATES), "своего «Акта» в чате нет"
    assert not any("Изменить" in title for title in titles)
    assert old_button.text == OWN_FILE_IN_APP_TEXT
