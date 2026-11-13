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


def _has_design_column() -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("sport_publications"):
        return False
    return any(c["name"] == "design" for c in insp.get_columns("sport_publications"))


def upgrade() -> None:
    if not _has_design_column():
        op.add_column(
            "sport_publications",
            sa.Column("design", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("sport_publications") and _has_design_column():
        op.drop_column("sport_publications", "design")
