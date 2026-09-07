"""Add origin marker to ForgeAI groups.

Revision ID: 20260907_0001
Revises: 1b9654c0c3d3
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0001"
down_revision: str | Sequence[str] | None = "1b9654c0c3d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="local"),
    )
    op.execute("UPDATE groups SET source = 'ad' WHERE ad_dn IS NOT NULL")


def downgrade() -> None:
    op.drop_column("groups", "source")
