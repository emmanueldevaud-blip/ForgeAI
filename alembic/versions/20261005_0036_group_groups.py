"""Add group_groups hierarchy table

Revision ID: 20261005_0036
Revises: 20261005_0035
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261005_0036'
down_revision = '20261005_0035'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'group_groups',
        sa.Column('parent_group_id', sa.Integer(), nullable=False),
        sa.Column('child_group_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['parent_group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['child_group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('parent_group_id', 'child_group_id'),
    )


def downgrade() -> None:
    op.drop_table('group_groups')
