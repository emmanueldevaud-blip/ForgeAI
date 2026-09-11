"""Remove Premise layer: Room attaches directly to Level.

Revision ID: 20260910_0001
Revises: 20260909_0002
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_0001"
down_revision: str | Sequence[str] | None = "20260909_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_fks_on_table(conn, table: str):
    """Drop all FK constraints on a table."""
    fks = conn.execute(sa.text(
        "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE CONSTRAINT_TYPE = 'FOREIGN KEY' AND TABLE_NAME = :t AND CONSTRAINT_SCHEMA = DATABASE()"
    ), {"t": table}).fetchall()
    for fk in fks:
        op.execute(f"ALTER TABLE {table} DROP FOREIGN KEY {fk[0]}")


def _drop_fk_referencing(conn, table: str, ref_table: str):
    """Drop FK on `table` that references `ref_table`."""
    fks = conn.execute(sa.text(
        "SELECT tc.CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS tc "
        "JOIN information_schema.KEY_COLUMN_USAGE kcu ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME "
        "JOIN information_schema.REFERENTIAL_CONSTRAINTS rc ON tc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME "
        "WHERE tc.CONSTRAINT_TYPE = 'FOREIGN KEY' AND tc.TABLE_NAME = :t "
        "AND rc.REFERENCED_TABLE_NAME = :r AND tc.CONSTRAINT_SCHEMA = DATABASE()"
    ), {"t": table, "r": ref_table}).fetchall()
    for fk in fks:
        op.execute(f"ALTER TABLE {table} DROP FOREIGN KEY {fk[0]}")


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add new columns to rooms (nullable initially)
    op.add_column("rooms", sa.Column("level_id", sa.Integer, nullable=True))
    op.add_column("rooms", sa.Column("reference", sa.String(50), nullable=True))
    op.add_column("rooms", sa.Column("usage_type_id", sa.Integer, nullable=True))

    # 2. Migrate data: copy from Premise → Room
    conn.execute(sa.text("""
        UPDATE rooms r
        JOIN premises p ON p.id = r.premise_id
        SET r.level_id = p.level_id,
            r.reference = p.reference,
            r.usage_type_id = p.usage_type_id
    """))

    # 3. Verify no orphan rooms
    orphans = conn.execute(sa.text(
        "SELECT COUNT(*) FROM rooms WHERE level_id IS NULL"
    )).scalar()
    if orphans and orphans > 0:
        raise Exception(
            f"{orphans} rooms have no level assigned after migration. Cannot proceed."
        )

    # 4. Make level_id NOT NULL
    op.alter_column("rooms", "level_id", sa.Integer, nullable=False)

    # 5. Add FK for level_id
    op.create_foreign_key(
        "fk_rooms_level_id", "rooms", "levels", ["level_id"], ["id"],
        ondelete="CASCADE",
    )

    # 6. Add FK for usage_type_id (nullable, SET NULL on delete)
    op.create_foreign_key(
        "fk_rooms_usage_type_id", "rooms", "usage_types", ["usage_type_id"], ["id"],
        ondelete="SET NULL",
    )

    # 7. Add unique constraint on (level_id, reference)
    op.create_unique_constraint(
        "uq_room_level_reference", "rooms", ["level_id", "reference"]
    )

    # 8. Add indexes
    op.create_index("ix_rooms_level_active", "rooms", ["level_id", "is_active"])
    op.create_index("ix_rooms_level_id", "rooms", ["level_id"])
    op.create_index("ix_rooms_usage_type_id", "rooms", ["usage_type_id"])

    # 9. Drop old premise_id index and FK, then drop column
    op.drop_index("ix_rooms_premise_active", table_name="rooms")
    _drop_fk_referencing(conn, "rooms", "premises")
    op.drop_column("rooms", "premise_id")

    # 10. Drop premises table (drop all FKs first)
    op.drop_index("ix_premises_level_active", table_name="premises")
    op.drop_index("ix_premises_level_id", table_name="premises")
    _drop_fks_on_table(conn, "premises")
    op.drop_table("premises")


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Recreate premises table
    op.create_table(
        "premises",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("level_id", sa.Integer, sa.ForeignKey("levels.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("reference", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("usage_type_id", sa.Integer, sa.ForeignKey("usage_types.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("area", sa.Numeric(10, 2), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("level_id", "reference", name="uq_premise_level_reference"),
    )
    op.create_index("ix_premises_level_active", "premises", ["level_id", "is_active"])
    op.create_index("ix_premises_level_id", "premises", ["level_id"])

    # 2. Populate premises from rooms (one premise per unique level_id + reference)
    conn.execute(sa.text("""
        INSERT INTO premises (level_id, reference, name, usage_type_id, area, description, is_active, created_at, updated_at)
        SELECT DISTINCT
            r.level_id,
            r.reference,
            r.name,
            r.usage_type_id,
            r.area,
            r.description,
            r.is_active,
            r.created_at,
            r.updated_at
        FROM rooms r
        WHERE r.level_id IS NOT NULL AND r.reference IS NOT NULL
    """))

    # 3. Add premise_id to rooms
    op.add_column("rooms", sa.Column("premise_id", sa.Integer, nullable=True))

    # 4. Link rooms to premises
    conn.execute(sa.text("""
        UPDATE rooms r
        JOIN premises p ON p.level_id = r.level_id AND p.reference = r.reference
        SET r.premise_id = p.id
    """))

    # 5. Make premise_id NOT NULL
    op.alter_column("rooms", "premise_id", sa.Integer, nullable=False)

    # 6. Add FK for premise_id
    op.create_foreign_key(
        "fk_rooms_premise_id", "rooms", "premises", ["premise_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_rooms_premise_active", "rooms", ["premise_id", "is_active"])

    # 7. Drop new columns and constraints from rooms
    op.execute("ALTER TABLE rooms DROP FOREIGN KEY fk_rooms_level_id")
    op.execute("ALTER TABLE rooms DROP FOREIGN KEY fk_rooms_usage_type_id")
    op.drop_constraint("uq_room_level_reference", "rooms", type_="unique")
    op.drop_index("ix_rooms_level_active", table_name="rooms")
    op.drop_index("ix_rooms_level_id", table_name="rooms")
    op.drop_index("ix_rooms_usage_type_id", table_name="rooms")
    op.drop_column("rooms", "level_id")
    op.drop_column("rooms", "reference")
    op.drop_column("rooms", "usage_type_id")
