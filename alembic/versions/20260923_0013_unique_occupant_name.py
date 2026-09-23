"""Prevent duplicate occupant names."""

from alembic import op


revision = "20260923_0013"
down_revision = "20260923_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_occupants_name", "occupants", ["last_name", "first_name"])


def downgrade() -> None:
    op.drop_constraint("uq_occupants_name", "occupants", type_="unique")
