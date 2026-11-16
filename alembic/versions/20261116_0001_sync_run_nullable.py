"""Rend nullable meta_analytics_sync_runs.account_id.

La trace de synchronisation est creee au debut du cycle, avant la resolution
du compte Meta : account_id n'est renseigne qu'ensuite (et reste nul si la
resolution echoue). La contrainte NOT NULL provoquait a chaque cycle
(1048, "Column 'account_id' cannot be null") et faisait echouer toute la
synchro Meta. Aucune donnee existante supprimee.

Revision ID: 20261116_0001_sync_run_nullable
Revises: 20261114_0001_meta_analytics
Create Date: 2026-11-16
"""

import sqlalchemy as sa

from alembic import op

revision = "20261116_0001_sync_run_nullable"
down_revision = "20261114_0001_meta_analytics"
branch_labels = None
depends_on = None

TABLE = "meta_analytics_sync_runs"
COLUMN = "account_id"


def _account_id_nullable():
    """Nullabilite actuelle de account_id, ou None si table/colonne absente."""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABLE):
        return None
    for col in insp.get_columns(TABLE):
        if col["name"] == COLUMN:
            return bool(col["nullable"])
    return None


def upgrade() -> None:
    if _account_id_nullable() is False:
        op.alter_column(
            TABLE,
            COLUMN,
            existing_type=sa.Integer(),
            nullable=True,
            existing_nullable=False,
        )


def downgrade() -> None:
    # Echoue si des lignes ont account_id NULL (trace d'execution non
    # retraçable) : a traiter manuellement avant un retour en arriere.
    if _account_id_nullable() is True:
        op.alter_column(
            TABLE,
            COLUMN,
            existing_type=sa.Integer(),
            nullable=False,
            existing_nullable=True,
        )
