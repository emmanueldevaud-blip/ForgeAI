"""Widen photos.byte_size to BIGINT

Revision ID: 20261005_0035
Revises: 20261003_0034
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261005_0035'
down_revision = '20261003_0034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # INT max = 2 147 483 647 (2,1 Go) : les vidéos dépassent ce seuil.
    op.alter_column(
        'photos', 'byte_size',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'photos', 'byte_size',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
