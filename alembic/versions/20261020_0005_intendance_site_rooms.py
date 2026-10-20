"""Associe les sites Intendance aux locaux des bâtiments."""

from alembic import op
import sqlalchemy as sa

revision = "20261020_0005"
down_revision = "20261020_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intendance_site_rooms",
        sa.Column("intendance_site_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["intendance_site_id"], ["intendance_sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("intendance_site_id", "room_id"),
        sa.UniqueConstraint("room_id", name="uq_intendance_site_rooms_room"),
    )


def downgrade() -> None:
    op.drop_table("intendance_site_rooms")
