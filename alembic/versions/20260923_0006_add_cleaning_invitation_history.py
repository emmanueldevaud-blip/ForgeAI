"""Add cleaning invitation status and send history."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0006"
down_revision = "20260923_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "housing_cleanings",
        sa.Column("invitation_status", sa.String(length=30), nullable=False, server_default="not_sent"),
    )
    op.create_table(
        "housing_cleaning_invitation_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cleaning_id", sa.Integer(), nullable=False),
        sa.Column("volunteer_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["cleaning_id"], ["housing_cleanings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["volunteer_id"], ["volunteers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_cleaning_invitation_logs_cleaning", "housing_cleaning_invitation_logs", ["cleaning_id"])
    op.create_index("ix_cleaning_invitation_logs_volunteer", "housing_cleaning_invitation_logs", ["volunteer_id"])


def downgrade() -> None:
    op.drop_index("ix_cleaning_invitation_logs_volunteer", table_name="housing_cleaning_invitation_logs")
    op.drop_index("ix_cleaning_invitation_logs_cleaning", table_name="housing_cleaning_invitation_logs")
    op.drop_table("housing_cleaning_invitation_logs")
    op.drop_column("housing_cleanings", "invitation_status")
