"""ORM-модели. Любое изменение = новая миграция: ``alembic revision --autogenerate``."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.db.types import BigIntPK, UtcDateTime


class Base(DeclarativeBase):
    pass


class User(Base):
    """Пользователь мини-аппа/бота. Ключ идентичности — user_id платформы MAX."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    max_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(255), default="")
    last_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255), index=True)
    language_code: Mapped[str | None] = mapped_column(String(16))
    photo_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # Откуда пользователь пришёл впервые: mini_app | bot.
    first_seen_via: Mapped[str] = mapped_column(String(16), default="mini_app")

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")

    @property
    def display_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or str(self.max_user_id)


class RefreshToken(Base):
    """Refresh-токен хранится хешем; сам токен уходит клиенту в httpOnly-cookie.

    ``family_id`` объединяет цепочку ротаций: повторное предъявление уже
    ротированного токена — признак кражи, вся семья отзывается.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[str] = mapped_column(
        String(36), index=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    replaced_by_hash: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
