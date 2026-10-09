"""Agenda : télétravail sans local (room_id nullable)

Le télétravail devient une présence indépendante des locaux : une seule
ligne par jour et par utilisateur, avec ``room_id NULL``. L'invariant
appliqué côté service est ``room_id IS NULL <=> is_remote = 1``.

Les lignes créées en v1 (``is_remote = 1`` avec un local) sont converties
en lignes sans local.

Revision ID: 20261008_0040
Revises: 20261008_0039
Create Date: 2026-10-08

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261008_0040'
down_revision = '20261008_0039'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    op.alter_column(
        'agenda_presences',
        'room_id',
        existing_type=sa.Integer(),
        existing_nullable=False,
        nullable=True,
    )
    if _has_column(bind, 'agenda_presences', 'is_remote'):
        # Conversion des télétravails v1 (liés à un local) en lignes sans local.
        op.execute(
            sa.text(
                "UPDATE agenda_presences SET room_id = NULL "
                "WHERE is_remote = 1 AND room_id IS NOT NULL"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, 'agenda_presences', 'room_id'):
        return
    # Les lignes sans local (télétravail) n'ont aucun local de référence :
    # elles sont retirées pour rétablir la contrainte NOT NULL.
    op.execute(sa.text("DELETE FROM agenda_presences WHERE room_id IS NULL"))
    op.alter_column(
        'agenda_presences',
        'room_id',
        existing_type=sa.Integer(),
        existing_nullable=True,
        nullable=False,
    )
