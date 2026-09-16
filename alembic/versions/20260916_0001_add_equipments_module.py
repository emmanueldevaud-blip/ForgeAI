"""add_equipments_module

Revision ID: 20260916_0001
Revises: 20260910_0001
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20260916_0001"
down_revision = "20260910_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_equipment_type_code"),
    )
    op.create_index("ix_equipment_types_code", "equipment_types", ["code"])
    op.create_index("ix_equipment_types_code_active", "equipment_types", ["code", "is_active"])

    op.create_table(
        "equipments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reference", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("equipment_type_id", sa.Integer(), nullable=True),
        sa.Column("manufacturer", sa.String(200), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("serial_number", sa.String(200), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("installation_date", sa.Date(), nullable=True),
        sa.Column("commissioning_date", sa.Date(), nullable=True),
        sa.Column("warranty_end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="en_service"),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_equipment_reference"),
        sa.ForeignKeyConstraint(["equipment_type_id"], ["equipment_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_equipments_reference", "equipments", ["reference"])
    op.create_index("ix_equipments_status", "equipments", ["status"])
    op.create_index("ix_equipments_room_id", "equipments", ["room_id"])
    op.create_index("ix_equipments_equipment_type_id", "equipments", ["equipment_type_id"])
    op.create_index("ix_equipments_type_active", "equipments", ["equipment_type_id", "is_active"])
    op.create_index("ix_equipments_room_active", "equipments", ["room_id", "is_active"])
    op.create_index("ix_equipments_status_active", "equipments", ["status", "is_active"])

    # Seed default equipment types
    equipment_types = [
        ("chauffage", "Chauffage", 1),
        ("climatisation", "Climatisation", 2),
        ("ventilation", "Ventilation", 3),
        ("electricite", "Électricité", 4),
        ("plomberie", "Plomberie", 5),
        ("sanitaire", "Sanitaire", 6),
        ("securite", "Sécurité", 7),
        ("incendie", "Incendie", 8),
        ("eclairage", "Éclairage", 9),
        ("informatique", "Informatique", 10),
        ("equipement_technique", "Équipement technique", 11),
        ("autre", "Autre", 12),
    ]
    for code, name, sort_order in equipment_types:
        op.execute(
            f"INSERT INTO equipment_types (code, name, sort_order, is_active) "
            f"VALUES ('{code}', '{name}', {sort_order}, 1)"
        )


def downgrade() -> None:
    op.drop_table("equipments")
    op.drop_table("equipment_types")
