"""Add ad_dn field to volunteers table

Revision ID: 20260925_0025
Revision ID Note: Add ad_dn field to volunteers table for AD linking

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260925_0025"
down_revision = "20260924_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volunteers",
        sa.Column("ad_dn", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("volunteers", "ad_dn")
