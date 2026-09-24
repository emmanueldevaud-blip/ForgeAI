"""Allow one agenda presence per user, day and room."""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0022_room_unique"
down_revision = "20260924_0021_agenda_needs_meal"
branch_labels = None
depends_on = None


def _index_exists(bind, index_name: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = 'agenda_presences'
              AND index_name = :name
            LIMIT 1
            """
        ),
        {"name": index_name},
    ).first()
    return bool(row)


def upgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind, "uq_agenda_presence_date_user"):
        op.drop_constraint(
            "uq_agenda_presence_date_user",
            "agenda_presences",
            type_="unique",
        )
    if not _index_exists(bind, "uq_agenda_presence_date_user_room"):
        op.create_unique_constraint(
            "uq_agenda_presence_date_user_room",
            "agenda_presences",
            ["presence_date", "user_id", "room_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind, "uq_agenda_presence_date_user_room"):
        op.drop_constraint(
            "uq_agenda_presence_date_user_room",
            "agenda_presences",
            type_="unique",
        )
    if not _index_exists(bind, "uq_agenda_presence_date_user"):
        op.create_unique_constraint(
            "uq_agenda_presence_date_user",
            "agenda_presences",
            ["presence_date", "user_id"],
        )
