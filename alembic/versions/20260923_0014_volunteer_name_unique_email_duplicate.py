"""Allow duplicate volunteer emails and prevent duplicate names."""

from alembic import op


revision = "20260923_0014"
down_revision = "20260923_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("email", "volunteers", type_="unique")
    op.create_unique_constraint("uq_volunteers_name", "volunteers", ["first_name", "last_name"])


def downgrade() -> None:
    op.drop_constraint("uq_volunteers_name", "volunteers", type_="unique")
    op.create_unique_constraint("email", "volunteers", ["email"])
