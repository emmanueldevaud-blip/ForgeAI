"""Merge story draft heads

Revision ID: 20261121_0001
Revises: 17895f11fb97, 20261120_0002
Create Date: 2026-11-21 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20261121_0001'
down_revision: Union[str, Sequence[str], None] = ('17895f11fb97', '20261120_0002')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
