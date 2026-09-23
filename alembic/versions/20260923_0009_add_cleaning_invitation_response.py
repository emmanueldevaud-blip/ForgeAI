"""Add public cleaning invitation response fields."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260923_0009"
down_revision = "20260923_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column("housing_cleaning_invitation_logs", sa.Column("response_token", sa.String(length=36), nullable=True))
        op.add_column("housing_cleaning_invitation_logs", sa.Column("availability_response", sa.String(length=20), nullable=True))
        op.execute("UPDATE housing_cleaning_invitation_logs SET response_token = UUID() WHERE response_token IS NULL")
        op.alter_column(
            "housing_cleaning_invitation_logs", "response_token",
            existing_type=sa.String(length=36), nullable=False,
        )
        op.create_index("ix_cleaning_invitation_logs_response_token", "housing_cleaning_invitation_logs", ["response_token"], unique=True)
        return

    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("housing_cleaning_invitation_logs")}
    if "response_token" not in columns:
        op.add_column("housing_cleaning_invitation_logs", sa.Column("response_token", sa.String(length=36), nullable=True))
    if "availability_response" not in columns:
        op.add_column("housing_cleaning_invitation_logs", sa.Column("availability_response", sa.String(length=20), nullable=True))
    op.execute("UPDATE housing_cleaning_invitation_logs SET response_token = UUID() WHERE response_token IS NULL")
    op.alter_column(
        "housing_cleaning_invitation_logs",
        "response_token",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    indexes = {index["name"] for index in inspector.get_indexes("housing_cleaning_invitation_logs")}
    if "ix_cleaning_invitation_logs_response_token" not in indexes:
        op.create_index("ix_cleaning_invitation_logs_response_token", "housing_cleaning_invitation_logs", ["response_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_cleaning_invitation_logs_response_token", table_name="housing_cleaning_invitation_logs")
    op.drop_column("housing_cleaning_invitation_logs", "availability_response")
    op.drop_column("housing_cleaning_invitation_logs", "response_token")
