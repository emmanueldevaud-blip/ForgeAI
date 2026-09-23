"""Add required volunteer count to housing cleanings."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0004"
down_revision = "20260923_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "housing_cleanings",
        sa.Column("volunteers_needed", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("housing_cleanings", "volunteers_needed")
