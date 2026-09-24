"""ORM-модели. Любое изменение = новая миграция: ``alembic revision --autogenerate``."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.db.types import BigIntPK, UtcDateTime

# Значения полей и спецификации шаблона — документы переменной формы: колонка
# вместо таблицы «поле-значение». В PostgreSQL это JSONB (индексируемый),
# в SQLite тестов — обычный JSON.
JsonDict = JSON().with_variant(JSONB, "postgresql")
# Необязательный документ: None пишется SQL NULL, а не JSON-литералом null.
NullableJson = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


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
    # Откуда пользователь пришёл впервые: mini_app | bot | reviewer (учётка проверяющих).
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


class CompanyProfile(Base):
    """Реквизиты самого пользователя: то, что в документе стоит со стороны продавца."""

    __tablename__ = "company_profiles"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    # Ключ → значение в каноническом виде домена (inn, kpp, bic, account, address...).
    values: Mapped[dict[str, str]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )


class Counterparty(Base):
    """Карточка контрагента: заполняется один раз, дальше подставляется в документы."""

    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    inn: Mapped[str | None] = mapped_column(String(12), index=True)
    values: Mapped[dict[str, str]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )


class Template(Base):
    """Шаблон документа: спецификация полей плюс тело для подстановки.

    ``owner_user_id`` пуст у встроенных шаблонов. Слуг уникален глобально:
    шаблон компании получит слуг с префиксом владельца, поэтому частичный
    индекс «уникально среди системных» не нужен.
    """

    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("slug", name="uq_templates_slug"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text, default="")
    fields: Mapped[list[dict[str, object]]] = mapped_column(JsonDict, default=list)
    body: Mapped[str] = mapped_column(Text, default="")
    body_format: Mapped[str] = mapped_column(String(16), default="text")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )


class Document(Base):
    """Заполняемый документ: шаблон плюс значения полей с их источниками."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id", ondelete="RESTRICT"))
    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # Ключ → {value, source, confidence, confirmed}: источник нужен предпросмотру,
    # подтверждение — правилу «распознанное утверждает человек».
    values: Mapped[dict[str, dict[str, object]]] = mapped_column(JsonDict, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )

    template: Mapped[Template] = relationship()
    counterparty: Mapped[Counterparty | None] = relationship()


class DocumentFile(Base):
    """Собранный файл документа: один актуальный на формат.

    Сам файл лежит на диске (``core.files.storage``), в базе — путь, размер и
    хеш: по хешу видно, что документ не пересобирали после правки полей.
    """

    __tablename__ = "document_files"
    __table_args__ = (UniqueConstraint("document_id", "format", name="uq_document_files_format"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[str] = mapped_column(String(8))
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(512))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    # Хеш текста, из которого собран файл: по нему видно, что документ правили после сборки.
    source_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )


class ChatState(Base):
    """Состояние диалога с ботом: над каким документом пользователь сейчас работает.

    Отдельная таблица, а не колонка в users: колонка дала бы циклический внешний
    ключ users ↔ documents, а здесь же живёт остальное состояние диалога.
    """

    __tablename__ = "chat_states"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    # Фото или скан, присланный до выбора документа: ссылка MAX, а не байты —
    # файл перекачивается, когда пользователь выберет, куда его распознать.
    pending_media: Mapped[dict[str, object] | None] = mapped_column(NullableJson)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), onupdate=func.now()
    )


class DocumentEvent(Base):
    """Факт из жизни документа: создан, готов, собран, отправлен, доставлен,
    отклонено значение. Из фактов собираются история пользователя и метрики.

    Журнал только пополняется. Удаление документа факты не стирает (document_id
    станет NULL): воронка и счётчик пойманных ошибок не должны переписывать
    прошлое, а персональных данных здесь нет — только вид, формат, код и время.
    """

    __tablename__ = "document_events"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    # Вид шаблона (invoice, offer, contract): метрики по видам переживают удаление документа.
    template_kind: Mapped[str | None] = mapped_column(String(32))
    format: Mapped[str | None] = mapped_column(String(8))
    # Код отказа: field.inn_invalid у отклонённого значения, max_api.403 у недоставки.
    code: Mapped[str | None] = mapped_column(String(64))
    # Откуда пришло: источник отклонённого значения или «copy» у документа-копии.
    source: Mapped[str | None] = mapped_column(String(16))
    # UUID события document.ready: по нему доставка сшивается с отправкой.
    event_id: Mapped[str | None] = mapped_column(String(64), index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now(), index=True)


class UserActivityDay(Base):
    """День, когда пользователь что-то делал: вход в мини-апп или реплика боту.

    Одна строка на пользователя и день — из них считаются активные за день и
    неделю; last_login_at в users хранит только последний вход.
    """

    __tablename__ = "user_activity_days"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
