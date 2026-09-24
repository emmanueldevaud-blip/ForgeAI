"""Add agenda room and workstation to occupancies.

Also backfills existing occupancies with the RIOM / BUREAUX room and workstation.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0023_occ_agenda_room"
down_revision = "20260924_0022_room_unique"
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).first()
    return bool(row)


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "occupancies", "agenda_room_id"):
        op.add_column(
            "occupancies",
            sa.Column("agenda_room_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_occupancies_agenda_room_id",
            "occupancies",
            "rooms",
            ["agenda_room_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_occupancies_agenda_room_id",
            "occupancies",
            ["agenda_room_id"],
        )
    if not _column_exists(bind, "occupancies", "needs_workstation"):
        op.add_column(
            "occupancies",
            sa.Column("needs_workstation", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # Existing occupancies → RIOM building, BUREAUX room, with workstation
    bind.execute(
        sa.text(
            """
            UPDATE occupancies o
            JOIN housings h ON h.id = o.housing_id
            JOIN rooms r ON r.id = h.room_id
            JOIN buildings b ON b.id = r.building_id
            SET o.agenda_room_id = (
                SELECT r2.id
                FROM rooms r2
                JOIN buildings b2 ON b2.id = r2.building_id
                WHERE b2.id = b.id
                  AND r2.is_active = 1
                  AND (
                    UPPER(r2.name) LIKE '%BUREAU%'
                    OR UPPER(r2.reference) LIKE '%BUREAU%'
                  )
                ORDER BY r2.id
                LIMIT 1
            ),
            o.needs_workstation = 1
            WHERE o.agenda_room_id IS NULL
            """
        )
    )
    # If housing is not in RIOM but RIOM has a BUREAUX room, use it as fallback
    bind.execute(
        sa.text(
            """
            UPDATE occupancies o
            SET o.agenda_room_id = (
                SELECT r2.id
                FROM rooms r2
                JOIN buildings b2 ON b2.id = r2.building_id
                WHERE UPPER(b2.name) LIKE '%RIOM%'
                  AND r2.is_active = 1
                  AND (
                    UPPER(r2.name) LIKE '%BUREAU%'
                    OR UPPER(r2.reference) LIKE '%BUREAU%'
                  )
                ORDER BY r2.id
                LIMIT 1
            ),
            o.needs_workstation = 1
            WHERE o.agenda_room_id IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "occupancies", "needs_workstation"):
        op.drop_column("occupancies", "needs_workstation")
    if _column_exists(bind, "occupancies", "agenda_room_id"):
        op.drop_index("ix_occupancies_agenda_room_id", table_name="occupancies")
        op.drop_constraint("fk_occupancies_agenda_room_id", "occupancies", type_="foreignkey")
        op.drop_column("occupancies", "agenda_room_id")
