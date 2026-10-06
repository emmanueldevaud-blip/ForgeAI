"""add group_groups table for AD group hierarchy

Revision ID: 20261006_1440
Revises: 20261006_0037
Create Date: 2026-10-06 14:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '20261006_1440'
down_revision = '20261006_0037'
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.drop_table('group_groups')

