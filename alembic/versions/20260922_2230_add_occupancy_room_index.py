"""add room index to occupancies

Revision ID: 20260922_2230
Revises: 20260922_2200
Create Date: 2026-09-22 22:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260922_2230"
down_revision = "20260922_2200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("occupancies")}
    if "room_index" not in columns:
        op.add_column("occupancies", sa.Column("room_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("occupancies", "room_index")
