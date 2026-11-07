"""Add MediaPublishToken table for secure media publishing.

Revision ID: 20261107_0002
Revises: 20261107_0001
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261107_0002"
down_revision = "20261107_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # media_publish_tokens
    op.create_table(
        "media_publish_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("photo_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_media_publish_token_hash"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_media_publish_token_hash", "media_publish_tokens", ["token_hash"], unique=True)
    op.create_index("ix_media_publish_token_photo", "media_publish_tokens", ["photo_id"])
    op.create_index("ix_media_publish_token_user", "media_publish_tokens", ["user_id"])
    op.create_index("ix_media_publish_token_expires", "media_publish_tokens", ["expires_at"])
    op.create_index("ix_media_publish_token_consumed", "media_publish_tokens", ["consumed"])


def downgrade() -> None:
    op.drop_index("ix_media_publish_token_consumed", table_name="media_publish_tokens")
    op.drop_index("ix_media_publish_token_expires", table_name="media_publish_tokens")
    op.drop_index("ix_media_publish_token_user", table_name="media_publish_tokens")
    op.drop_index("ix_media_publish_token_photo", table_name="media_publish_tokens")
    op.drop_index("ix_media_publish_token_hash", table_name="media_publish_tokens")
    op.drop_table("media_publish_tokens")