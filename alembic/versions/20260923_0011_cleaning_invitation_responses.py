"""Store cleaning invitation response times."""

from alembic import op


revision = "20260923_0011"
down_revision = "20260923_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE housing_cleaning_invitation_logs "
        "ADD COLUMN response_at DATETIME NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE housing_cleaning_invitation_logs "
        "DROP COLUMN response_at"
    )
