"""Store asynchronous Sport activity AI analysis state."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0017_sport_ai"
down_revision = "20260923_0016_sport_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sport_activity_analyses", sa.Column("ai_status", sa.String(30), nullable=False, server_default="pending"))
    op.add_column("sport_activity_analyses", sa.Column("ai_analysis_json", sa.JSON(), nullable=True))
    op.add_column("sport_activity_analyses", sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_sport_activity_analyses_ai_status", "sport_activity_analyses", ["ai_status"])


def downgrade() -> None:
    op.drop_index("ix_sport_activity_analyses_ai_status", table_name="sport_activity_analyses")
    op.drop_column("sport_activity_analyses", "ai_generated_at")
    op.drop_column("sport_activity_analyses", "ai_analysis_json")
    op.drop_column("sport_activity_analyses", "ai_status")
