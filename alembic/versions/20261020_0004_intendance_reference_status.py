"""Ajoute le statut actif des catégories, codes et utilisateurs Intendance."""
from alembic import op
import sqlalchemy as sa

revision = "20261020_0004"
down_revision = "20261020_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("intendance_account_codes", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("intendance_card_aliases", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("intendance_categories", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("intendance_categories", "is_active")
    op.drop_column("intendance_card_aliases", "is_active")
    op.drop_column("intendance_account_codes", "is_active")
