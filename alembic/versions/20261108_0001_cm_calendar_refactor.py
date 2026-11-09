"""Add content_type/source fields to EditorialCalendarEntry and SportPublication.

Revision ID: 20261108_0001
Revises: 4ea90591ddaf
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261108_0001"
down_revision = "4ea90591ddaf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "editorial_calendar_entries",
        sa.Column("content_type", sa.String(length=50), nullable=False, server_default="manuel"),
    )
    op.add_column(
        "editorial_calendar_entries",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manuel"),
    )
    op.add_column(
        "editorial_calendar_entries",
        sa.Column("source_activity_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "editorial_calendar_entries",
        sa.Column("photo_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_editorial_calendar_entries_content_type",
        "editorial_calendar_entries",
        ["content_type"],
    )
    op.create_index(
        "ix_editorial_calendar_entries_source",
        "editorial_calendar_entries",
        ["source"],
    )
    op.create_foreign_key(
        "fk_editorial_calendar_entries_source_activity",
        "editorial_calendar_entries",
        "sport_activities",
        ["source_activity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_editorial_calendar_entries_photo",
        "editorial_calendar_entries",
        "photos",
        ["photo_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "sport_publications",
        sa.Column("content_type", sa.String(length=50), nullable=False, server_default="publication_sportive"),
    )
    op.add_column(
        "sport_publications",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manuel"),
    )
    op.create_index(
        "ix_sport_publications_content_type",
        "sport_publications",
        ["content_type"],
    )
    op.create_index(
        "ix_sport_publications_source",
        "sport_publications",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index("ix_sport_publications_source", table_name="sport_publications")
    op.drop_index("ix_sport_publications_content_type", table_name="sport_publications")
    op.drop_column("sport_publications", "source")
    op.drop_column("sport_publications", "content_type")
    op.drop_constraint("fk_editorial_calendar_entries_photo", table_name="editorial_calendar_entries", type_="foreignkey")
    op.drop_constraint("fk_editorial_calendar_entries_source_activity", table_name="editorial_calendar_entries", type_="foreignkey")
    op.drop_index("ix_editorial_calendar_entries_source", table_name="editorial_calendar_entries")
    op.drop_index("ix_editorial_calendar_entries_content_type", table_name="editorial_calendar_entries")
    op.drop_column("editorial_calendar_entries", "photo_id")
    op.drop_column("editorial_calendar_entries", "source_activity_id")
    op.drop_column("editorial_calendar_entries", "source")
    op.drop_column("editorial_calendar_entries", "content_type")
