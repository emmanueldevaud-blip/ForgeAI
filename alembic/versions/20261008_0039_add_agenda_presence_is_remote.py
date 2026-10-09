"""Ajoute agenda_presences.is_remote (inscription en télétravail)

Un télétravail compte comme une présence dans le local mais ne consomme
ni poste de travail ni repas (``needs_workstation`` / ``needs_meal``
forcés à False côté service).

Revision ID: 20261008_0039
Revises: 20261007_0038
Create Date: 2026-10-08

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261008_0039'
down_revision = '20261007_0038'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, 'agenda_presences', 'is_remote'):
        op.add_column(
            'agenda_presences',
            sa.Column('is_remote', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, 'agenda_presences', 'is_remote'):
        op.drop_column('agenda_presences', 'is_remote')
