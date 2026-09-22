"""Associate email template attachments with housings."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0001"
down_revision = "20260922_2230"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "housing_email_attachment_housings",
        sa.Column("attachment_id", sa.Integer(), nullable=False),
        sa.Column("housing_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["attachment_id"], ["housing_email_template_attachments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["housing_id"], ["housings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("attachment_id", "housing_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_email_attachment_housings_attachment", "housing_email_attachment_housings", ["attachment_id"])
    op.create_index("ix_email_attachment_housings_housing", "housing_email_attachment_housings", ["housing_id"])


def downgrade() -> None:
    op.drop_index("ix_email_attachment_housings_housing", table_name="housing_email_attachment_housings")
    op.drop_index("ix_email_attachment_housings_attachment", table_name="housing_email_attachment_housings")
    op.drop_table("housing_email_attachment_housings")
