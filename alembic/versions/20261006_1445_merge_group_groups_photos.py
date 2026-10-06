"""merge group_groups and photos migrations

Revision ID: 20261006_1445
Revises: 20261003_0034, 20261006_1440
Create Date: 2026-10-06 14:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261006_1445'
down_revision = ('20261003_0034', '20261006_1440')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

