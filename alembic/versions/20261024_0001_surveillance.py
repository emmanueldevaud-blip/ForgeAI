"""Add surveillance camera and recording metadata tables."""
from alembic import op
import sqlalchemy as sa

revision = "20261024_0001"
down_revision = "789e745528aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "surveillance_cameras",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("location", sa.String(160), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("protocol", sa.String(20), nullable=True),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("stream_url", sa.String(500), nullable=True),
        sa.Column("username", sa.String(160), nullable=True),
        sa.Column("encrypted_password", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detection_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_surveillance_cameras_enabled", "surveillance_cameras", ["enabled"])
    op.create_table(
        "surveillance_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["surveillance_cameras.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_surveillance_events_camera_created", "surveillance_events", ["camera_id", "created_at"])
    op.create_table(
        "surveillance_recordings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["surveillance_cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["surveillance_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_surveillance_recordings_camera_created", "surveillance_recordings", ["camera_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_surveillance_recordings_camera_created", table_name="surveillance_recordings")
    op.drop_table("surveillance_recordings")
    op.drop_index("ix_surveillance_events_camera_created", table_name="surveillance_events")
    op.drop_table("surveillance_events")
    op.drop_index("ix_surveillance_cameras_enabled", table_name="surveillance_cameras")
    op.drop_table("surveillance_cameras")
