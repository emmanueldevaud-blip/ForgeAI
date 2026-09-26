"""Add phone field to users table

Revision ID: 20260926_0026
Revision ID Note: Add phone field to users table for AD synchronisation

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260926_0026"
down_revision = "20260925_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "phone")
