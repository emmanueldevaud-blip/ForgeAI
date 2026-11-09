"""merge heads

Revision ID: 3fc12e785388
Revises: 20261107_0004, 20261107_0005
Create Date: 2026-11-07 11:21:58.360751
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3fc12e785388"
down_revision = ("20261107_0004", "20261107_0005")
branch_labels = None
depends_on = None

# This is a merge migration - no operations needed
