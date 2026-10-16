"""Ajout du local (room_id) sur les plages reseau du parc informatique."""

from alembic import op
import sqlalchemy as sa


revision = "20261016_0011"
down_revision = "20261016_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("it_network_ranges", schema=None) as batch_op:
        batch_op.add_column(sa.Column("room_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_it_network_ranges_room_id_rooms",
            "rooms",
            ["room_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_network_ranges_room_active",
            ["room_id", "is_active"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("it_network_ranges", schema=None) as batch_op:
        batch_op.drop_index("ix_network_ranges_room_active")
        batch_op.drop_constraint("fk_it_network_ranges_room_id_rooms", type_="foreignkey")
        batch_op.drop_column("room_id")
