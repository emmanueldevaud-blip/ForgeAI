"""add occupancy guest_type column

Revision ID: f002b341a3bf
Revises: 6e3ce94b89bf
Create Date: 2026-09-22 16:49:28.517303

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f002b341a3bf'
down_revision: Union[str, Sequence[str], None] = '6e3ce94b89bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("occupancies", sa.Column("guest_type", sa.String(20), nullable=True))
    pass


def downgrade() -> None:
    pass