"""Ajoute la visibilité des codes et utilisateurs dans le tableau de bord."""
from alembic import op
import sqlalchemy as sa

revision = "20261020_0003"
down_revision = "20261020_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("intendance_account_codes", sa.Column("dashboard_visible", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("intendance_card_aliases", sa.Column("dashboard_visible", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("intendance_card_aliases", "dashboard_visible")
    op.drop_column("intendance_account_codes", "dashboard_visible")
