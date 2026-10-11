"""merge heads

Revision ID: ba51ae6eea49
Revises: 20261006_1445, 20261008_0040
Create Date: 2026-10-09 10:36:09.463981

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba51ae6eea49'
down_revision: Union[str, Sequence[str], None] = ('20261006_1445', '20261008_0040')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass