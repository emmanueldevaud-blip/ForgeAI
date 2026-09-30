"""Add sport_agent_executions and sport_recommendations tables

Revision ID: 20260930_0032
Revision ID Note: Agent Sport autonome - executions, decisions et recommandations

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260930_0032"
down_revision = "20260929_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sport_agent_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("athlete_id", sa.Integer(), nullable=True),
        sa.Column("objective_id", sa.Integer(), nullable=True),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="running"),
        sa.Column("step_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("steps_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["objective_id"], ["sport_goals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_sport_agent_executions_user_id", "sport_agent_executions", ["user_id"])
    op.create_index("ix_sport_agent_executions_athlete_id", "sport_agent_executions", ["athlete_id"])
    op.create_index("ix_sport_agent_executions_objective_id", "sport_agent_executions", ["objective_id"])
    op.create_index("ix_sport_agent_executions_trigger", "sport_agent_executions", ["trigger", "started_at"])
    op.create_index("ix_sport_agent_executions_status", "sport_agent_executions", ["status"])
    op.create_index("ix_sport_agent_executions_athlete_status", "sport_agent_executions", ["athlete_id", "status"])

    op.create_table(
        "sport_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("objective_id", sa.Integer(), nullable=True),
        sa.Column("execution_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(40), nullable=False, server_default="training"),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["objective_id"], ["sport_goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["execution_id"], ["sport_agent_executions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_sport_recommendations_athlete_id", "sport_recommendations", ["athlete_id"])
    op.create_index("ix_sport_recommendations_user_id", "sport_recommendations", ["user_id"])
    op.create_index("ix_sport_recommendations_objective_id", "sport_recommendations", ["objective_id"])
    op.create_index("ix_sport_recommendations_execution_id", "sport_recommendations", ["execution_id"])
    op.create_index("ix_sport_recommendations_status", "sport_recommendations", ["status"])
    op.create_index("ix_sport_recommendations_athlete_status", "sport_recommendations", ["athlete_id", "status"])
    op.create_index("ix_sport_recommendations_created", "sport_recommendations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sport_recommendations_created", table_name="sport_recommendations")
    op.drop_index("ix_sport_recommendations_athlete_status", table_name="sport_recommendations")
    op.drop_index("ix_sport_recommendations_status", table_name="sport_recommendations")
    op.drop_index("ix_sport_recommendations_execution_id", table_name="sport_recommendations")
    op.drop_index("ix_sport_recommendations_objective_id", table_name="sport_recommendations")
    op.drop_index("ix_sport_recommendations_user_id", table_name="sport_recommendations")
    op.drop_index("ix_sport_recommendations_athlete_id", table_name="sport_recommendations")
    op.drop_table("sport_recommendations")
    op.drop_index("ix_sport_agent_executions_athlete_status", table_name="sport_agent_executions")
    op.drop_index("ix_sport_agent_executions_status", table_name="sport_agent_executions")
    op.drop_index("ix_sport_agent_executions_trigger", table_name="sport_agent_executions")
    op.drop_index("ix_sport_agent_executions_objective_id", table_name="sport_agent_executions")
    op.drop_index("ix_sport_agent_executions_athlete_id", table_name="sport_agent_executions")
    op.drop_index("ix_sport_agent_executions_user_id", table_name="sport_agent_executions")
    op.drop_table("sport_agent_executions")
