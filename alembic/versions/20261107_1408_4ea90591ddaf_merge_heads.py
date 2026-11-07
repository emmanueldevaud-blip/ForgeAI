"""merge heads

Revision ID: 4ea90591ddaf
Revises: 20261107_0004, 20261107_0006
Create Date: 2026-11-07 14:08:06.119396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ea90591ddaf'
down_revision: Union[str, Sequence[str], None] = ('20261107_0004', '20261107_0006')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass