"""Store volunteers selected after invitation responses."""

from alembic import op


revision = "20260923_0012"
down_revision = "20260923_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE housing_cleanings "
        "ADD COLUMN selected_volunteer_ids_json TEXT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE housing_cleanings "
        "DROP COLUMN selected_volunteer_ids_json"
    )
