"""Add agenda module: presence planning and workstation capacity on rooms."""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0019_agenda"
down_revision = "20260923_0018_sport_retry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rooms",
        sa.Column("workstation_capacity", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "agenda_presences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("presence_date", sa.Date(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("external_name", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_ref", sa.String(length=100), nullable=True),
        sa.Column("is_present", sa.Boolean(), nullable=False),
        sa.Column("needs_workstation", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("presence_date", "user_id", name="uq_agenda_presence_date_user"),
    )
    op.create_index("ix_agenda_presences_presence_date", "agenda_presences", ["presence_date"])
    op.create_index("ix_agenda_presences_room_id", "agenda_presences", ["room_id"])
    op.create_index("ix_agenda_presences_user_id", "agenda_presences", ["user_id"])
    op.create_index(
        "ix_agenda_presences_date_room", "agenda_presences", ["presence_date", "room_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_agenda_presences_date_room", table_name="agenda_presences")
    op.drop_index("ix_agenda_presences_user_id", table_name="agenda_presences")
    op.drop_index("ix_agenda_presences_room_id", table_name="agenda_presences")
    op.drop_index("ix_agenda_presences_presence_date", table_name="agenda_presences")
    op.drop_table("agenda_presences")
    op.drop_column("rooms", "workstation_capacity")
