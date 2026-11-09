"""merge heads

Revision ID: 20261109_0002
Revises: 20261109_0001, b4bcb6a9cb24
Create Date: 2026-11-09 09:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20261109_0002'
down_revision: Union[str, Sequence[str], None] = ('20261109_0001', 'b4bcb6a9cb24')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
