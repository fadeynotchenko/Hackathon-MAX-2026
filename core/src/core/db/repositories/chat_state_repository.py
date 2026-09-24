"""Состояние диалога с ботом: одна строка на пользователя."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import ChatState


class ChatStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_document_id(self, user_id: int) -> int | None:
        state = await self._session.get(ChatState, user_id)
        return state.document_id if state is not None else None

    async def set_active_document(self, user_id: int, document_id: int | None) -> None:
        state = await self._session.get(ChatState, user_id)
        if state is None:
            state = ChatState(user_id=user_id)
            self._session.add(state)
        state.document_id = document_id
        await self._session.flush()
