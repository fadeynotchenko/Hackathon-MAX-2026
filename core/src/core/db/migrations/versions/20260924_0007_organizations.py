"""organizations: несколько своих организаций вместо одной company_profiles

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

JSON_DICT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=True),
        sa.Column("values", JSON_DICT, nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_user_id", "organizations", ["user_id"], unique=False)
    # Прежняя «моя организация» становится основной; пустые заготовки не переносим.
    op.execute(
        """
        INSERT INTO organizations (user_id, name, inn, "values", is_default, created_at, updated_at)
        SELECT user_id, name, NULLIF("values"->>'inn', ''), "values", true, created_at, updated_at
        FROM company_profiles
        WHERE name <> '' OR "values" <> '{}'::jsonb
        """
    )
    op.add_column("documents", sa.Column("organization_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_documents_organization_id_organizations",
        "documents",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Старые документы — от прежней организации: «на основе этого» возьмёт её же.
    op.execute(
        """
        UPDATE documents AS d SET organization_id = o.id
        FROM organizations AS o
        WHERE o.user_id = d.user_id AND o.is_default
        """
    )
    op.drop_table("company_profiles")


def downgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("values", JSON_DICT, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_company_profiles_user_id", "company_profiles", ["user_id"], unique=True)
    op.execute(
        """
        INSERT INTO company_profiles (user_id, name, "values", created_at, updated_at)
        SELECT user_id, name, "values", created_at, updated_at FROM organizations WHERE is_default
        """
    )
    op.drop_constraint("fk_documents_organization_id_organizations", "documents", type_="foreignkey")
    op.drop_column("documents", "organization_id")
    op.drop_index("ix_organizations_user_id", table_name="organizations")
    op.drop_table("organizations")
