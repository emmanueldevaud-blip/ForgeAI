"""Make activity_id nullable in sport_publications for calendar-based publications.

Revision ID: 20261107_0004
Revises: 20261107_0001
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "20261107_0004"
down_revision = "20261107_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # 1. Drop the unique constraint on activity_id
    # MySQL stores it as an index, so we drop the index
    try:
        op.drop_index("uq_sport_publication_activity", table_name="sport_publications")
    except Exception:
        pass
    
    # 2. Make activity_id nullable
    op.alter_column(
        "sport_publications",
        "activity_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_nullable=False,
    )
    
    # 3. Recreate the unique index on activity_id (allows multiple NULLs in MySQL)
    try:
        op.create_index("uq_sport_publication_activity", "sport_publications", ["activity_id"], unique=True)
    except Exception:
        pass


def downgrade() -> None:
    conn = op.get_bind()
    
    # Drop the unique index
    try:
        op.drop_index("uq_sport_publication_activity", table_name="sport_publications")
    except Exception:
        pass
    
    # Make activity_id NOT NULL again
    op.alter_column(
        "sport_publications",
        "activity_id",
        existing_type=sa.Integer(),
        nullable=False,
        existing_nullable=True,
    )
    
    # Recreate unique constraint
    try:
        op.create_index("uq_sport_publication_activity", "sport_publications", ["activity_id"], unique=True)
    except Exception:
        pass
