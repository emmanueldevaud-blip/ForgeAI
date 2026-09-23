"""Track Sport activity AI analysis retries and failures."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0018_sport_retry"
down_revision = "20260923_0017_sport_ai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sport_activity_analyses", sa.Column("ai_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sport_activity_analyses", sa.Column("ai_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sport_activity_analyses", "ai_error")
    op.drop_column("sport_activity_analyses", "ai_attempts")
