"""Состояние диалога с ботом: одна строка на пользователя."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import ChatState


class ChatStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _state(self, user_id: int) -> ChatState:
        state = await self._session.get(ChatState, user_id)
        if state is None:
            state = ChatState(user_id=user_id)
            self._session.add(state)
        return state

    async def active_document_id(self, user_id: int) -> int | None:
        state = await self._session.get(ChatState, user_id)
        return state.document_id if state is not None else None

    async def set_active_document(self, user_id: int, document_id: int | None) -> None:
        state = await self._state(user_id)
        state.document_id = document_id
        await self._session.flush()

    async def set_pending_media(self, user_id: int, media: dict[str, object] | None) -> None:
        state = await self._state(user_id)
        state.pending_media = media
        await self._session.flush()

    async def pending_media(self, user_id: int) -> dict[str, object] | None:
        state = await self._session.get(ChatState, user_id)
        return state.pending_media if state is not None else None

    async def take_pending_media(self, user_id: int) -> dict[str, object] | None:
        """Забрать отложенное вложение: второй раз то же фото не распознаётся."""
        state = await self._session.get(ChatState, user_id)
        if state is None or state.pending_media is None:
            return None
        media, state.pending_media = state.pending_media, None
        await self._session.flush()
        return media
