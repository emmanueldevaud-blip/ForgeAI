"""Add volunteer communication preference."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0008"
down_revision = "20260923_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volunteers",
        sa.Column("communication_preference", sa.String(length=10), nullable=False, server_default="both"),
    )


def downgrade() -> None:
    op.drop_column("volunteers", "communication_preference")
