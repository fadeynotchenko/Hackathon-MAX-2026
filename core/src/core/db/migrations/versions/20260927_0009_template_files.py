"""template_files: свой шаблон из файла-образца DOCX

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_template_files_owner_user_id", "template_files", ["owner_user_id"], unique=False)
    op.add_column("templates", sa.Column("file_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_templates_file_id_template_files", "templates", "template_files", ["file_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_templates_file_id_template_files", "templates", type_="foreignkey")
    op.drop_column("templates", "file_id")
    op.drop_index("ix_template_files_owner_user_id", table_name="template_files")
    op.drop_table("template_files")
