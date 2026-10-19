"""Ajout des champs d'URL de gestion (interface web) sur it_assets.

Colonne NULLables uniquement : compatible avec la base existante,
aucune donnee existante n'est modifiee.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261019_0001"
down_revision = "20261016_0012"
branch_labels = None
depends_on = None


_COLUMNS = [
    sa.Column("management_url", sa.String(length=500), nullable=True),
    sa.Column("management_url_detected_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("management_url_status", sa.String(length=20), nullable=True),
    sa.Column("management_url_source", sa.String(length=20), nullable=True),
]


def upgrade() -> None:
    for column in _COLUMNS:
        op.add_column("it_assets", column)


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column("it_assets", column.name)
