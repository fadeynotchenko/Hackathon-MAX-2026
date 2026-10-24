"""chat_states.last_change: что помощник поменял последним, для «Отменить»

Прежние значения полей, которые записало последнее сообщение, фото или голосовое
в чате: кнопка «Отменить» и слова «верни как было» возвращают их. Хранится одно
изменение — отменяется последнее, истории правок здесь нет.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_DICT = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("chat_states", sa.Column("last_change", JSON_DICT, nullable=True))


def downgrade() -> None:
    op.drop_column("chat_states", "last_change")
