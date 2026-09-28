"""template_files: бланки встроенных шаблонов и раскладка текста для предпросмотра

Встроенные счёт, КП и договор теперь собираются в файлах-бланках DOCX, как
свои шаблоны из образца: у их файлов нет владельца. ``layout`` — текст образца
для предпросмотра, где строка таблицы — одна строка, а не столбик ячеек.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("template_files", "owner_user_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("template_files", sa.Column("layout", sa.Text(), nullable=True))


def downgrade() -> None:
    # Шаблоны на бланках без владельца становятся текстовыми: текст у них есть.
    op.execute(
        "UPDATE templates SET file_id = NULL, body_format = 'text' "
        "WHERE file_id IN (SELECT id FROM template_files WHERE owner_user_id IS NULL)"
    )
    op.execute("DELETE FROM template_files WHERE owner_user_id IS NULL")
    op.drop_column("template_files", "layout")
    op.alter_column("template_files", "owner_user_id", existing_type=sa.BigInteger(), nullable=False)
