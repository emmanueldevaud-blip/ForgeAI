"""Add Instagram media fields to SportPublication.

Revision ID: 20261107_0001
Revises: 20261106_0002
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261107_0001"
down_revision = "20261106_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Instagram media fields to sport_publications
    op.add_column(
        "sport_publications",
        sa.Column("instagram_media_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "sport_publications",
        sa.Column("instagram_permalink", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sport_publications", "instagram_permalink")
    op.drop_column("sport_publications", "instagram_media_id")