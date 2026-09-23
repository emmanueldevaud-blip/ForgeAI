"""Normalize pending cleaning records to not planned."""

from alembic import op


revision = "20260923_0010"
down_revision = "20260923_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE housing_cleanings AS c "
        "SET status = 'not_planned' "
        "WHERE c.status = 'planned' "
        "AND c.invitation_status = 'not_sent' "
        "AND NOT EXISTS ("
        "SELECT 1 FROM cleaning_volunteers AS cv WHERE cv.cleaning_id = c.id"
        ")"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE housing_cleanings AS c "
        "SET status = 'planned' "
        "WHERE c.status = 'not_planned'"
    )
