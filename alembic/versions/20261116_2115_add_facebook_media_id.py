"""Add facebook_media_id and facebook_permalink to sport_publications

Revision ID: a4253b421645
Revises: 20261117_0001_cm_strategy
Create Date: 2026-11-16 21:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4253b421645'
down_revision = '20261117_0001_cm_strategy'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add facebook_media_id and facebook_permalink columns to sport_publications
    op.add_column('sport_publications', sa.Column('facebook_media_id', sa.String(255), nullable=True))
    op.add_column('sport_publications', sa.Column('facebook_permalink', sa.Text, nullable=True))


def downgrade() -> None:
    # Remove the columns
    op.drop_column('sport_publications', 'facebook_permalink')
    op.drop_column('sport_publications', 'facebook_media_id')
