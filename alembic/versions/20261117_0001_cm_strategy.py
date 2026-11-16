"""Ajoute les champs de la strategie editoriale Jepepagtrail.

Revision ID: 20261117_0001_cm_strategy
Revises: 20261116_0001_sync_run_nullable
Create Date: 2026-11-17
"""

import sqlalchemy as sa

from alembic import op

revision = "20261117_0001_cm_strategy"
down_revision = "20261116_0001_sync_run_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "community_manager_strategies",
        sa.Column("signature_hashtag", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "community_manager_strategies",
        sa.Column("editorial_objective", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "community_manager_strategies",
        sa.Column("editorial_pillars", sa.JSON(), nullable=True),
    )
    op.add_column(
        "community_manager_strategies",
        sa.Column("max_hashtags", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "community_manager_strategies",
        sa.Column("human_validation_required", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "community_manager_strategies",
        sa.Column("auto_publish", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("community_manager_strategies", "auto_publish")
    op.drop_column("community_manager_strategies", "human_validation_required")
    op.drop_column("community_manager_strategies", "max_hashtags")
    op.drop_column("community_manager_strategies", "editorial_pillars")
    op.drop_column("community_manager_strategies", "editorial_objective")
    op.drop_column("community_manager_strategies", "signature_hashtag")
