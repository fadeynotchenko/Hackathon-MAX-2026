"""organizations: подпись и печать картинками

Картинка лежит рядом с реквизитами организации и ставится в её документы.
Хеш — отдельной колонкой: он входит в ключ кеша листов и в признак устаревания
файла, и ради него не нужно читать саму картинку.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for kind in ("signature", "stamp"):
        op.add_column("organizations", sa.Column(kind, sa.LargeBinary(), nullable=True))
        op.add_column("organizations", sa.Column(f"{kind}_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    for kind in ("signature", "stamp"):
        op.drop_column("organizations", f"{kind}_sha256")
        op.drop_column("organizations", kind)
