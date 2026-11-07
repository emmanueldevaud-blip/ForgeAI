"""Add lock fields to SportPublication for UX control.

Revision ID: 20261107_0006
Revises: 20261107_0005
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261107_0006"
down_revision = "20261107_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sport_publications", sa.Column("title_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("sport_publications", sa.Column("content_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("sport_publications", sa.Column("photo_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("sport_publications", "photo_locked")
    op.drop_column("sport_publications", "content_locked")
    op.drop_column("sport_publications", "title_locked")