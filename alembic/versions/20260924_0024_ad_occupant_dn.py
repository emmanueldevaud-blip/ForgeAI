"""Add ad_dn field to occupants table

Revision ID: 20260924_0024
Revision ID Note: Add ad_dn field to occupants table for AD linking

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260924_0024"
down_revision = "20260924_0023_occ_agenda_room"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "occupants",
        sa.Column("ad_dn", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("occupants", "ad_dn")
