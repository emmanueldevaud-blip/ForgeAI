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


def _column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    result = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column"
        ),
        {"table": table_name, "column": column_name}
    )
    return result.scalar() > 0


def upgrade() -> None:
    conn = op.get_bind()

    # Add new columns only if they don't exist
    columns_to_add = [
        ("calendar_entry_id", sa.Column("calendar_entry_id", sa.Integer(), sa.ForeignKey("editorial_calendar_entries.id", ondelete="SET NULL"), nullable=True)),
        ("tone_used", sa.Column("tone_used", sa.String(50), nullable=True)),
        ("visual_generation_prompt", sa.Column("visual_generation_prompt", sa.Text(), nullable=True)),
        ("visual_generation_provider", sa.Column("visual_generation_provider", sa.String(50), nullable=True)),
        ("created_from", sa.Column("created_from", sa.String(20), nullable=True)),
        ("validated_at", sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True)),
        ("scheduled_at", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True)),
        ("failed_at", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True)),
        ("error_message", sa.Column("error_message", sa.Text(), nullable=True)),
    ]

    for col_name, col_def in columns_to_add:
        if not _column_exists(conn, "sport_publications", col_name):
            op.add_column("sport_publications", col_def)

    # Add indexes only if they don't exist (MySQL doesn't support IF NOT EXISTS for indexes easily)
    # We'll try to create them and ignore errors if they exist
    try:
        op.create_index("ix_sport_publications_calendar_entry", "sport_publications", ["calendar_entry_id"])
    except Exception:
        pass

    try:
        op.create_index("ix_sport_publications_created_from", "sport_publications", ["created_from"])
    except Exception:
        pass

    # Update existing records to have created_from='activity'
    op.execute("UPDATE sport_publications SET created_from = 'activity' WHERE created_from IS NULL")


def downgrade() -> None:
    # Drop indexes
    try:
        op.drop_index("ix_sport_publications_created_from", table_name="sport_publications")
    except Exception:
        pass
    try:
        op.drop_index("ix_sport_publications_calendar_entry", table_name="sport_publications")
    except Exception:
        pass

    # Drop columns
    columns_to_drop = [
        "error_message",
        "failed_at",
        "scheduled_at",
        "validated_at",
        "created_from",
        "visual_generation_provider",
        "visual_generation_prompt",
        "tone_used",
        "calendar_entry_id",
    ]
    for col_name in columns_to_drop:
        try:
            op.drop_column("sport_publications", col_name)
        except Exception:
            pass