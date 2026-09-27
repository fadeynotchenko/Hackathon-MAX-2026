"""templates: у своего шаблона — вид документа, как у стандартных

Свои шаблоны получали общий вид custom; теперь человек выбирает счёт, КП,
договор или другой документ. Прежние свои шаблоны — «другой документ».

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE templates SET kind = 'other' WHERE kind = 'custom'")
    op.execute("UPDATE document_events SET template_kind = 'other' WHERE template_kind = 'custom'")


def downgrade() -> None:
    op.execute(
        "UPDATE templates SET kind = 'custom' WHERE owner_user_id IS NOT NULL AND kind = 'other'"
    )
