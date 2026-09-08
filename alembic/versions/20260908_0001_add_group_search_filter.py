"""Add configurable group search filter to ADConfig.

Revision ID: 20260908_0001
Revises: 20260907_0001
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0001"
down_revision: str | Sequence[str] | None = "20260907_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ad_configs",
        sa.Column(
            "group_search_filter",
            sa.String(length=255),
            nullable=False,
            server_default="(&(objectCategory=group)(cn=GG_FORGEAI*))",
        ),
    )


def downgrade() -> None:
    op.drop_column("ad_configs", "group_search_filter")
