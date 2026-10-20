"""Ajoute la visibilité indépendante des sites dans le tableau de bord."""
from alembic import op
import sqlalchemy as sa

revision = "20261020_0002"
down_revision = "20261020_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("intendance_sites", sa.Column("dashboard_visible", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("intendance_sites", "dashboard_visible")
