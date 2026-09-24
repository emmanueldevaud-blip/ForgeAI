"""Add period (half-day) on agenda_presences."""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0020_agenda_period"
down_revision = "20260924_0019_agenda"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agenda_presences",
        sa.Column(
            "period",
            sa.String(length=10),
            nullable=False,
            server_default="full",
        ),
    )


def downgrade() -> None:
    op.drop_column("agenda_presences", "period")
