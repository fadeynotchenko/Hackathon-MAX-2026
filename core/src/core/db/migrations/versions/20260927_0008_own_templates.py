"""templates: свои шаблоны пользователя — архив редакций и удалённых

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("templates", sa.Column("origin_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_templates_origin_id_templates",
        "templates",
        "templates",
        ["origin_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_templates_origin_id_templates", "templates", type_="foreignkey")
    op.drop_column("templates", "origin_id")
    op.drop_column("templates", "archived_at")
