"""Ajout du compteur d'echecs consecutifs sur it_assets pour l'hysteresis."""

from alembic import op
import sqlalchemy as sa


revision = "20261016_0012"
down_revision = "20261016_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("it_assets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("it_assets", schema=None) as batch_op:
        batch_op.drop_column("consecutive_failures")
