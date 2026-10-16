"""Rendre le local des équipements du parc informatique facultatif."""

from alembic import op
import sqlalchemy as sa


revision = "20261016_0010"
down_revision = "20261012_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "it_assets",
        "room_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.drop_constraint("it_assets_ibfk_1", "it_assets", type_="foreignkey")
    op.create_foreign_key(
        "it_assets_ibfk_1",
        "it_assets",
        "rooms",
        ["room_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    raise RuntimeError("Impossible de rendre room_id obligatoire sans réaffecter les équipements sans local")
