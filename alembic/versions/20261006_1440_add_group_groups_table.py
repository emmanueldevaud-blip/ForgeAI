"""add group_groups table for AD group hierarchy

Revision ID: 20261006_1440
Revises: 20260908_0002
Create Date: 2026-10-06 14:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '20261006_1440'
down_revision = '20260908_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent : la table est déjà créée par 20261005_0036 sur l'autre branche
    # (les deux branches sont fusionnées par 20261006_1445 / ba51ae6eea49).
    bind = op.get_bind()
    if sa.inspect(bind).has_table('group_groups'):
        return
    op.create_table(
        'group_groups',
        sa.Column('parent_group_id', sa.Integer(), nullable=False),
        sa.Column('child_group_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.ForeignKeyConstraint(['child_group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('parent_group_id', 'child_group_id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('group_groups'):
        return
    op.drop_table('group_groups')

