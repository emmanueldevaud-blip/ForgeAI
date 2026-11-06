"""Add V2 fields to SportPublication for Community Manager integration.

Revision ID: 20261106_0002
Revises: 20261106_0001_community_manager
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "20261106_0002"
down_revision = "20261106_0001_community_manager"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to sport_publications
    op.add_column(
        "sport_publications",
        sa.Column("calendar_entry_id", sa.Integer(), sa.ForeignKey("editorial_calendar_entries.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("tone_used", sa.String(50), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("visual_generation_prompt", sa.Text(), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("visual_generation_provider", sa.String(50), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("created_from", sa.String(20), nullable=True),  # 'activity' or 'calendar'
    )
    op.add_column(
        "sport_publications",
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    # Add indexes
    op.create_index("ix_sport_publications_calendar_entry", "sport_publications", ["calendar_entry_id"])
    op.create_index("ix_sport_publications_created_from", "sport_publications", ["created_from"])

    # Update existing records to have created_from='activity'
    op.execute("UPDATE sport_publications SET created_from = 'activity' WHERE created_from IS NULL")


def downgrade() -> None:
    op.drop_index("ix_sport_publications_created_from", table_name="sport_publications")
    op.drop_index("ix_sport_publications_calendar_entry", table_name="sport_publications")
    op.drop_column("sport_publications", "error_message")
    op.drop_column("sport_publications", "failed_at")
    op.drop_column("sport_publications", "scheduled_at")
    op.drop_column("sport_publications", "validated_at")
    op.drop_column("sport_publications", "created_from")
    op.drop_column("sport_publications", "visual_generation_provider")
    op.drop_column("sport_publications", "visual_generation_prompt")
    op.drop_column("sport_publications", "tone_used")
    op.drop_column("sport_publications", "calendar_entry_id")