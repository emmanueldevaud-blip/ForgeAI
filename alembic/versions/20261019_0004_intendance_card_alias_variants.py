"""Ajoute les variantes de titulaires présentes dans les exports bancaires."""

from alembic import op
import sqlalchemy as sa


revision = "20261019_0004"
down_revision = "20261019_0003"
branch_labels = None
depends_on = None


_ALIASES = [
    ("(3031534_279) CB Partel C.", "PARTEL"),
    ("(3019418_279) CB Berthoud M.", "BERTHOUD"),
    ("(3121424_284) CB E Devaud", "DEVAUD"),
    ("(3013389) CB S Le Gall", "LE GALL"),
    ("(3024533_284) CB A Rosello", "ROSELLO"),
    ("(3031534) CB C Partel", "PARTEL"),
    ("", "HUB"),
]


def upgrade():
    bind = op.get_bind()
    for alias, user_name in _ALIASES:
        bind.execute(
            sa.text(
                "INSERT IGNORE INTO intendance_card_aliases (alias, user_name) "
                "VALUES (:alias, :user_name)"
            ),
            {"alias": alias, "user_name": user_name},
        )


def downgrade():
    bind = op.get_bind()
    for alias, user_name in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM intendance_card_aliases "
                "WHERE alias = :alias AND user_name = :user_name"
            ),
            {"alias": alias, "user_name": user_name},
        )
