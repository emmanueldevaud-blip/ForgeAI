"""Add V2 fields to SportPublication for Community Manager integration.

Revision ID: 20261107_0005
Revises: 20261107_0002
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "20261107_0005"
down_revision = "20261107_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add V2 fields to sport_publications
    op.add_column(
        "sport_publications",
        sa.Column("created_from", sa.String(20), nullable=True),
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
    op.add_column(
        "sport_publications",
        sa.Column("instagram_media_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("instagram_permalink", sa.Text(), nullable=True),
    )

    # Add indexes
    op.create_index("ix_sport_publications_calendar_entry", "sport_publications", ["calendar_entry_id"])
    op.create_index("ix_sport_publications_created_from", "sport_publications", ["created_from"])
    op.create_index("ix_sport_publications_instagram_media_id", "sport_publications", ["instagram_media_id"])


def downgrade() -> None:
    op.drop_index("ix_sport_publications_instagram_media_id", table_name="sport_publications")
    op.drop_index("ix_sport_publications_created_from", table_name="sport_publications")
    op.drop_index("ix_sport_publications_calendar_entry", table_name="sport_publications")
    op.drop_column("sport_publications", "instagram_permalink")
    op.drop_column("sport_publications", "instagram_media_id")
    op.drop_column("sport_publications", "error_message")
    op.drop_column("sport_publications", "failed_at")
    op.drop_column("sport_publications", "scheduled_at")
    op.drop_column("sport_publications", "validated_at")
    op.drop_column("sport_publications", "created_from")
