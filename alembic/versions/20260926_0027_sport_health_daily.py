"""Add sport_health_daily table

Revision ID: 20260926_0027
Revision ID Note: Store daily Garmin health metrics (sleep, HRV, stress, ...)

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260926_0027"
down_revision = "20260926_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sport_health_daily",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="garmin"),
        sa.Column("health_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_sport_health_daily_athlete_id", "sport_health_daily", ["athlete_id"])
    op.create_index("ix_sport_health_daily_day", "sport_health_daily", ["day"])
    op.create_index("uq_sport_health_daily", "sport_health_daily", ["athlete_id", "day", "source_type"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_sport_health_daily", table_name="sport_health_daily")
    op.drop_index("ix_sport_health_daily_day", table_name="sport_health_daily")
    op.drop_index("ix_sport_health_daily_athlete_id", table_name="sport_health_daily")
    op.drop_table("sport_health_daily")
