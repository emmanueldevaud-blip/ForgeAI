"""Add volunteer usage and cleaning assignments."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260923_0005"
down_revision = "20260923_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            "volunteers",
            sa.Column("usage_type", sa.String(length=50), nullable=False, server_default="cleaning"),
        )
        op.create_table(
            "cleaning_volunteers",
            sa.Column("cleaning_id", sa.Integer(), nullable=False),
            sa.Column("volunteer_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["cleaning_id"], ["housing_cleanings.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["volunteer_id"], ["volunteers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("cleaning_id", "volunteer_id"),
            mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("ix_cleaning_volunteers_cleaning", "cleaning_volunteers", ["cleaning_id"])
        op.create_index("ix_cleaning_volunteers_volunteer", "cleaning_volunteers", ["volunteer_id"])
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "usage_type" not in {column["name"] for column in inspector.get_columns("volunteers")}:
        op.add_column(
            "volunteers",
            sa.Column("usage_type", sa.String(length=50), nullable=False, server_default="cleaning"),
        )

    # Older deployments used cleaning_volunteers as the volunteer directory.
    # Preserve those records before reusing the table name for assignments.
    if "cleaning_volunteers" in tables:
        columns = {column["name"] for column in inspector.get_columns("cleaning_volunteers")}
        if {"last_name", "first_name"}.issubset(columns):
            op.execute(sa.text("""
                INSERT INTO volunteers (first_name, last_name, email, phone, is_active, usage_type)
                SELECT old.first_name, old.last_name, old.email, old.phone, old.is_active, old.usage_type
                FROM cleaning_volunteers old
                WHERE NOT EXISTS (
                    SELECT 1 FROM volunteers current
                    WHERE (old.email IS NOT NULL AND old.email <> '' AND current.email = old.email)
                       OR (current.first_name = old.first_name
                           AND current.last_name = old.last_name
                           AND COALESCE(current.phone, '') = COALESCE(old.phone, ''))
                )
            """))
            if "legacy_cleaning_volunteers" not in tables:
                op.rename_table("cleaning_volunteers", "legacy_cleaning_volunteers")

    if "cleaning_volunteers" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "cleaning_volunteers",
            sa.Column("cleaning_id", sa.Integer(), nullable=False),
            sa.Column("volunteer_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["cleaning_id"], ["housing_cleanings.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["volunteer_id"], ["volunteers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("cleaning_id", "volunteer_id"),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("ix_cleaning_volunteers_cleaning", "cleaning_volunteers", ["cleaning_id"])
        op.create_index("ix_cleaning_volunteers_volunteer", "cleaning_volunteers", ["volunteer_id"])


def downgrade() -> None:
    op.drop_index("ix_cleaning_volunteers_volunteer", table_name="cleaning_volunteers")
    op.drop_index("ix_cleaning_volunteers_cleaning", table_name="cleaning_volunteers")
    op.drop_table("cleaning_volunteers")
    op.drop_column("volunteers", "usage_type")
