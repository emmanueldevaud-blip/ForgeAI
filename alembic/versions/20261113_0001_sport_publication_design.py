"""Ajoute la colonne design sur sport_publications (éditeur graphique du Studio).

Colonne nullable JSON stockant la composition éditable (éléments texte,
stickers, images, carrousel, format). Aucune donnee existante modifiee.

Revision ID: 20261113_0001
Revises: 20261111_0001
Create Date: 2026-11-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20261113_0001"
down_revision = "20261111_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("sport_publications") and not insp.has_column(
        "sport_publications", "design"
    ):
        op.add_column(
            "sport_publications",
            sa.Column("design", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("sport_publications") and insp.has_column(
        "sport_publications", "design"
    ):
        op.drop_column("sport_publications", "design")
