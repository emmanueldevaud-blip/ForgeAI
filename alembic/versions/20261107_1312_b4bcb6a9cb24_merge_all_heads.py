"""merge all heads

Revision ID: b4bcb6a9cb24
Revises: aeb0bd7d124d, 4ea90591ddaf
Create Date: 2026-11-07 13:12:45.234870

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4bcb6a9cb24'
down_revision: Union[str, Sequence[str], None] = ('aeb0bd7d124d', '4ea90591ddaf')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass