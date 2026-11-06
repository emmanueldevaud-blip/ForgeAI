"""Add Community Manager tables: strategy and editorial calendar.

Revision ID: 20261106_0001_community_manager
Revises: 20261105_0002
Create Date: 2026-11-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "20261106_0001_community_manager"
down_revision = "20261105_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # community_manager_strategies
    op.create_table(
        "community_manager_strategies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("brand_identity", sa.String(length=200), nullable=True),
        sa.Column("tone", sa.JSON(), nullable=False),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("objectives", sa.JSON(), nullable=False),
        sa.Column("themes", sa.JSON(), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("networks", sa.JSON(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("forbidden_topics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("athlete_id", name="uq_community_manager_strategy_athlete"),
        sa.CheckConstraint("frequency >= 1 AND frequency <= 14", name="ck_frequency_range"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_community_manager_strategy_athlete",
        "community_manager_strategies",
        ["athlete_id"],
        unique=False,
    )

    # editorial_calendar_entries
    op.create_table(
        "editorial_calendar_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("theme", sa.String(length=100), nullable=True),
        sa.Column("objective", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'brouillon'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["community_manager_strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "theme IS NULL OR theme IN ('running','recovery','nutrition','training','gear','mental','races','lifestyle')",
            name="ck_theme_valid"
        ),
        sa.CheckConstraint(
            "objective IS NULL OR objective IN ('engagement','visibility','brand_awareness','community_building','lead_generation')",
            name="ck_objective_valid"
        ),
        sa.CheckConstraint(
            "status IN ('brouillon','planifié','publié','refusé')",
            name="ck_status_valid"
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_editorial_calendar_strategy_date",
        "editorial_calendar_entries",
        ["strategy_id", "date"],
        unique=False,
    )
    op.create_index(
        "ix_editorial_calendar_status",
        "editorial_calendar_entries",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_editorial_calendar_status", table_name="editorial_calendar_entries")
    op.drop_index("ix_editorial_calendar_strategy_date", table_name="editorial_calendar_entries")
    op.drop_table("editorial_calendar_entries")
    op.drop_index("ix_community_manager_strategy_athlete", table_name="community_manager_strategies")
    op.drop_table("community_manager_strategies")