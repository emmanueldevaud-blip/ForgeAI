"""add housing room names

Revision ID: 20260922_2200
Revises: f002b341a3bf
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260922_2200"
down_revision: Union[str, Sequence[str], None] = "f002b341a3bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("housings", sa.Column("room_names", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("housings", "room_names")
