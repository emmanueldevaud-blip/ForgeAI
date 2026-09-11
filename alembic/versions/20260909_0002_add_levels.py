"""Add levels table and migrate premises hierarchy.

Revision ID: 20260909_0002
Revises: 20260909_0001
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_0002"
down_revision: str | Sequence[str] | None = "20260909_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create levels table
    op.create_table(
        "levels",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("building_id", sa.Integer, sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("reference", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("level_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("building_id", "reference", name="uq_level_building_reference"),
    )
    op.create_index("ix_levels_building_active", "levels", ["building_id", "is_active"])

    # 2. Add level_id to premises (nullable initially)
    op.add_column("premises", sa.Column("level_id", sa.Integer, nullable=True))

    # 3. Migrate data: create levels from premises.floor values
    conn = op.get_bind()

    # Create levels for each unique (building_id, floor) pair
    conn.execute(sa.text("""
        INSERT INTO levels (building_id, reference, name, level_order, is_active, created_at, updated_at)
        SELECT DISTINCT
            p.building_id,
            COALESCE(p.floor, 'NIVEAU_1'),
            COALESCE(p.floor, 'Niveau 1'),
            1,
            1,
            NOW(),
            NOW()
        FROM premises p
        WHERE p.floor IS NOT NULL
        ON DUPLICATE KEY UPDATE name = VALUES(name)
    """))

    # Create default level for buildings with premises having NULL floor
    conn.execute(sa.text("""
        INSERT INTO levels (building_id, reference, name, level_order, is_active, created_at, updated_at)
        SELECT DISTINCT
            p.building_id,
            'NIVEAU_1',
            'Niveau 1',
            1,
            1,
            NOW(),
            NOW()
        FROM premises p
        WHERE p.floor IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM levels l
            WHERE l.building_id = p.building_id AND l.reference = 'NIVEAU_1'
        )
        ON DUPLICATE KEY UPDATE name = VALUES(name)
    """))

    # Update level_id on each premise
    conn.execute(sa.text("""
        UPDATE premises p
        JOIN levels l ON l.building_id = p.building_id
            AND l.reference = COALESCE(p.floor, 'NIVEAU_1')
        SET p.level_id = l.id
    """))

    # 4. Verify no orphan premises
    orphans = conn.execute(sa.text(
        "SELECT COUNT(*) FROM premises WHERE level_id IS NULL"
    )).scalar()
    if orphans and orphans > 0:
        raise Exception(
            f"{orphans} premises have no level assigned. Migration cannot proceed."
        )

    # 5. Make level_id NOT NULL
    op.alter_column("premises", "level_id", sa.Integer, nullable=False)

    # 6. Add FK for level_id
    op.create_foreign_key(
        "fk_premises_level_id", "premises", "levels", ["level_id"], ["id"],
        ondelete="CASCADE",
    )

    # 7. Drop old columns and constraints from premises
    op.drop_constraint("uq_premise_building_reference", "premises", type_="unique")
    op.execute("ALTER TABLE premises DROP FOREIGN KEY premises_ibfk_1")
    op.drop_index("ix_premises_building_id", table_name="premises")
    op.drop_column("premises", "building_id")
    op.drop_column("premises", "floor")

    # 8. Add new constraint and indexes
    op.create_unique_constraint(
        "uq_premise_level_reference", "premises", ["level_id", "reference"]
    )
    op.create_index("ix_premises_level_active", "premises", ["level_id", "is_active"])
    op.create_index("ix_premises_level_id", "premises", ["level_id"])


def downgrade() -> None:
    # Drop FK for level_id and new indexes/constraints
    op.execute("ALTER TABLE premises DROP FOREIGN KEY fk_premises_level_id")
    op.drop_constraint("uq_premise_level_reference", "premises", type_="unique")
    op.drop_index("ix_premises_level_active", table_name="premises")
    op.drop_index("ix_premises_level_id", table_name="premises")

    # Drop level_id
    op.drop_column("premises", "level_id")

    # Reverse: restore premises.building_id and premises.floor
    op.add_column("premises", sa.Column("building_id", sa.Integer, nullable=True))
    op.add_column("premises", sa.Column("floor", sa.String(50), nullable=True))

    # Restore building_id from level -> building
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE premises p
        JOIN levels l ON l.id = p.level_id
        SET p.building_id = l.building_id
    """))

    # Make building_id NOT NULL
    op.alter_column("premises", "building_id", sa.Integer, nullable=False)

    # Restore floor from level name
    conn.execute(sa.text("""
        UPDATE premises p
        JOIN levels l ON l.id = p.level_id
        SET p.floor = l.name
    """))

    # Restore old constraint and index
    op.create_unique_constraint(
        "uq_premise_building_reference", "premises", ["building_id", "reference"]
    )
    op.create_index("ix_premises_building_id", "premises", ["building_id"])

    # Restore FK for building_id
    op.create_foreign_key(
        "premises_ibfk_1", "premises", "buildings", ["building_id"], ["id"],
        ondelete="CASCADE",
    )

    # Drop levels table
    op.drop_index("ix_levels_building_active", table_name="levels")
    op.drop_table("levels")
