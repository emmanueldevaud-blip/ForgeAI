"""Add composite index on sport_activities (athlete_id, sport_type, started_at).

Supports the similar-activities lookup in SportService._calculate_activity_analysis,
which filters by athlete_id + sport_type and orders by started_at DESC. Without this
index MySQL sorts wide rows in a small sort buffer and fails with
'Out of sort memory' (error 1038).
"""

from alembic import op

revision = "20261104_0001"
down_revision = "20261024_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_sport_activities_athlete_sport_started",
        "sport_activities",
        ["athlete_id", "sport_type", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sport_activities_athlete_sport_started",
        table_name="sport_activities",
    )
