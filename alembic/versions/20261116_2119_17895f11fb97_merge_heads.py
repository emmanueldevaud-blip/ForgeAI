"""Merge heads

Revision ID: 17895f11fb97
Revises: a4253b421645, 20261118_0001_sp_companion_video
Create Date: 2026-11-16 21:19:30.178948

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17895f11fb97'
down_revision: Union[str, Sequence[str], None] = ('a4253b421645', '20261118_0001_sp_companion_video')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass