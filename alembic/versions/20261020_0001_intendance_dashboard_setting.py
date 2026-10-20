"""Ajoute le réglage d'affichage des dépenses non classées."""
from alembic import op
import sqlalchemy as sa

revision = "20261020_0001"
down_revision = "20261019_0005"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("intendance_dashboard_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exclude_uncategorized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

def downgrade():
    op.drop_table("intendance_dashboard_settings")
