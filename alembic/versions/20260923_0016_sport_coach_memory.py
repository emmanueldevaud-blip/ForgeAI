"""Add isolated Sport Coach conversations and observations."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0016_sport_memory"
down_revision = "20260923_0015_sport_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sport_coach_conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_sport_coach_conversations_athlete_id", "sport_coach_conversations", ["athlete_id"])
    op.create_table(
        "sport_coach_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("sources_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["sport_coach_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_sport_coach_messages_conversation_id", "sport_coach_messages", ["conversation_id"])
    op.create_table(
        "sport_athlete_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False, server_default="observed"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="calculated"),
        sa.Column("sources_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["sport_activities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_sport_athlete_observations_athlete_id", "sport_athlete_observations", ["athlete_id"])
    op.create_index("ix_sport_athlete_observations_activity_id", "sport_athlete_observations", ["activity_id"])
    op.create_index("ix_sport_athlete_observations_status", "sport_athlete_observations", ["status"])


def downgrade() -> None:
    op.drop_table("sport_athlete_observations")
    op.drop_table("sport_coach_messages")
    op.drop_table("sport_coach_conversations")
