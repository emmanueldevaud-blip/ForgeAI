"""add housing room config

Revision ID: ac372105c838
Revises: d791f3e28cfe
Create Date: 2026-09-19 07:51:06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ac372105c838'
down_revision: Union[str, Sequence[str], None] = 'd791f3e28cfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('housings', sa.Column('nb_rooms', sa.Integer(), server_default='1', nullable=False))
    op.add_column('housings', sa.Column('bed_configuration', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('housings', 'bed_configuration')
    op.drop_column('housings', 'nb_rooms')
