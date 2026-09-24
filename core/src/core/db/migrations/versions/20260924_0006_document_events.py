"""document_events и user_activity_days: факты для истории и метрик

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("template_kind", sa.String(length=32), nullable=True),
        sa.Column("format", sa.String(length=8), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column("event_id", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_events_user_id", "document_events", ["user_id"], unique=False)
    op.create_index("ix_document_events_document_id", "document_events", ["document_id"], unique=False)
    op.create_index("ix_document_events_event_id", "document_events", ["event_id"], unique=False)
    op.create_index("ix_document_events_created_at", "document_events", ["created_at"], unique=False)
    op.create_table(
        "user_activity_days",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.create_index("ix_user_activity_days_day", "user_activity_days", ["day"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_activity_days_day", table_name="user_activity_days")
    op.drop_table("user_activity_days")
    op.drop_index("ix_document_events_created_at", table_name="document_events")
    op.drop_index("ix_document_events_event_id", table_name="document_events")
    op.drop_index("ix_document_events_document_id", table_name="document_events")
    op.drop_index("ix_document_events_user_id", table_name="document_events")
    op.drop_table("document_events")
