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


def _columns_exist() -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns("community_manager_strategies")}


def upgrade() -> None:
    existing = _columns_exist()
    if "signature_hashtag" not in existing:
        op.add_column(
            "community_manager_strategies",
            sa.Column("signature_hashtag", sa.String(length=100), nullable=True),
        )
    if "editorial_objective" not in existing:
        op.add_column(
            "community_manager_strategies",
            sa.Column("editorial_objective", sa.String(length=100), nullable=True),
        )
    if "editorial_pillars" not in existing:
        op.add_column(
            "community_manager_strategies",
            sa.Column("editorial_pillars", sa.JSON(), nullable=True),
        )
    if "max_hashtags" not in existing:
        op.add_column(
            "community_manager_strategies",
            sa.Column("max_hashtags", sa.Integer(), nullable=False, server_default="5"),
        )
    if "human_validation_required" not in existing:
        op.add_column(
            "community_manager_strategies",
            sa.Column("human_validation_required", sa.Boolean(), nullable=False, server_default="1"),
        )
    if "auto_publish" not in existing:
        op.add_column(
            "community_manager_strategies",
            sa.Column("auto_publish", sa.Boolean(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    existing = _columns_exist()
    for column in (
        "auto_publish",
        "human_validation_required",
        "max_hashtags",
        "editorial_pillars",
        "editorial_objective",
        "signature_hashtag",
    ):
        if column in existing:
            op.drop_column("community_manager_strategies", column)
