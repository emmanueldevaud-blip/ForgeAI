"""Persist deterministic Sport activity analyses."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260923_0015_sport_analysis"
down_revision = "20260923_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and "sport_activity_analyses" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "sport_activity_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("analysis_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="calculated"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["sport_activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
def downgrade() -> None:
    op.drop_table("sport_activity_analyses")
