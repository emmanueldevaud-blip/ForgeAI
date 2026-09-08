"""Add ad_config_id to Group for AD config ownership tracking.

Revision ID: 20260908_0002
Revises: 20260908_0001
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0002"
down_revision: str | Sequence[str] | None = "20260908_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column(
            "ad_config_id",
            sa.Integer,
            sa.ForeignKey("ad_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_groups_ad_config_id", "groups", ["ad_config_id"])


def downgrade() -> None:
    op.drop_index("ix_groups_ad_config_id", table_name="groups")
    op.drop_column("groups", "ad_config_id")
