"""Add sport_analyses, notifications and push subscriptions tables

Revision ID: 20260927_0028
Revision ID Note: Automatic sport analyses (morning/evening/activity) + generic notifications

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260927_0028"
down_revision = "20260926_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sport_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("analysis_type", sa.String(20), nullable=False),
        sa.Column("analysis_day", sa.Date(), nullable=False),
        sa.Column("dedupe_key", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("notification_sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["sport_activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_sport_analyses_athlete_id", "sport_analyses", ["athlete_id"])
    op.create_index("ix_sport_analyses_activity_id", "sport_analyses", ["activity_id"])
    op.create_index("ix_sport_analyses_analysis_type", "sport_analyses", ["analysis_type"])
    op.create_index("ix_sport_analyses_analysis_day", "sport_analyses", ["analysis_day"])
    op.create_index("uq_sport_analysis_dedupe", "sport_analyses", ["athlete_id", "dedupe_key"], unique=True)
    op.create_index("ix_sport_analyses_athlete_generated", "sport_analyses", ["athlete_id", "generated_at"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="system"),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("push_sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_category", "notifications", ["category"])
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])

    op.create_table(
        "notification_push_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(200), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_notification_push_subscriptions_user_id", "notification_push_subscriptions", ["user_id"])
    op.create_index("uq_notification_push_endpoint", "notification_push_subscriptions", ["user_id", "endpoint"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_notification_push_endpoint", table_name="notification_push_subscriptions")
    op.drop_index("ix_notification_push_subscriptions_user_id", table_name="notification_push_subscriptions")
    op.drop_table("notification_push_subscriptions")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_index("ix_notifications_category", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_sport_analyses_athlete_generated", table_name="sport_analyses")
    op.drop_index("uq_sport_analysis_dedupe", table_name="sport_analyses")
    op.drop_index("ix_sport_analyses_analysis_day", table_name="sport_analyses")
    op.drop_index("ix_sport_analyses_analysis_type", table_name="sport_analyses")
    op.drop_index("ix_sport_analyses_activity_id", table_name="sport_analyses")
    op.drop_index("ix_sport_analyses_athlete_id", table_name="sport_analyses")
    op.drop_table("sport_analyses")
