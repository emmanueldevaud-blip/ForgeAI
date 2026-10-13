"""users.default_needs_workstation (préférence poste)

Préférence utilisateur : à l'inscription Agenda, le poste de travail est
auto-coché si la préférence est active (désactivée par défaut).

Revision ID: 20261012_0041
Revises: 202610100215_it_asset_v2
Create Date: 2026-10-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261012_0041'
down_revision = '202610100215_it_asset_v2'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, 'users', 'default_needs_workstation'):
        op.add_column(
            'users',
            sa.Column(
                'default_needs_workstation',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('0'),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, 'users', 'default_needs_workstation'):
        op.drop_column('users', 'default_needs_workstation')
