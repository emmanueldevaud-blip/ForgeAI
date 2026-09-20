"""add_housing_types

Revision ID: d791f3e28cfe
Revises: 20260918_0001
Create Date: 2026-09-19 07:39:17.749042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd791f3e28cfe'
down_revision: Union[str, Sequence[str], None] = '20260918_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'housing_types',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_housing_types_code'),
    )
    op.create_index('ix_housing_types_code', 'housing_types', ['code'], unique=True)
    op.create_index('ix_housing_types_code_active', 'housing_types', ['code', 'is_active'])


def downgrade() -> None:
    op.drop_index('ix_housing_types_code_active', table_name='housing_types')
    op.drop_index('ix_housing_types_code', table_name='housing_types')
    op.drop_table('housing_types')
