"""Add needs_meal on agenda_presences."""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0021_agenda_needs_meal"
down_revision = "20260924_0020_agenda_period"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agenda_presences",
        sa.Column(
            "needs_meal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("agenda_presences", "needs_meal")
