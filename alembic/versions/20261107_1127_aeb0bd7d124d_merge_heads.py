"""merge heads

Revision ID: aeb0bd7d124d
Revises: 20261107_0006, 3fc12e785388
Create Date: 2026-11-07 11:27:33.030365

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aeb0bd7d124d'
down_revision: Union[str, Sequence[str], None] = ('20261107_0006', '3fc12e785388')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass