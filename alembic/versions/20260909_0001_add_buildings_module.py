"""Add buildings module tables.

Revision ID: 20260909_0001
Revises: 20260908_0002
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_0001"
down_revision: str | Sequence[str] | None = "20260908_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Usage types
    op.create_table(
        "usage_types",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_types_code_active", "usage_types", ["code", "is_active"])

    # Room types
    op.create_table(
        "room_types",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_room_types_code_active", "room_types", ["code", "is_active"])

    # Sites
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("reference", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("address_complement", sa.String(500), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("city", sa.String(200), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sites_reference_active", "sites", ["reference", "is_active"])

    # Buildings
    op.create_table(
        "buildings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("site_id", sa.Integer, sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("reference", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("building_number", sa.String(50), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("floors_count", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("site_id", "reference", name="uq_building_site_reference"),
    )
    op.create_index("ix_buildings_site_active", "buildings", ["site_id", "is_active"])

    # Premises
    op.create_table(
        "premises",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("building_id", sa.Integer, sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("reference", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("usage_type_id", sa.Integer, sa.ForeignKey("usage_types.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("floor", sa.String(50), nullable=True),
        sa.Column("area", sa.Numeric(10, 2), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("building_id", "reference", name="uq_premise_building_reference"),
    )
    op.create_index("ix_premises_building_active", "premises", ["building_id", "is_active"])

    # Rooms
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("premise_id", sa.Integer, sa.ForeignKey("premises.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("room_type_id", sa.Integer, sa.ForeignKey("room_types.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("area", sa.Numeric(10, 2), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rooms_premise_active", "rooms", ["premise_id", "is_active"])

    # Seed initial usage types
    op.execute("""
        INSERT INTO usage_types (code, name, description, is_active, sort_order) VALUES
        ('BUREAUX', 'Bureaux', 'Espaces de bureau', 1, 1),
        ('LOGEMENT', 'Logement', 'Logements et appartements', 1, 2)
    """)

    # Seed initial room types
    op.execute("""
        INSERT INTO room_types (code, name, description, is_active, sort_order) VALUES
        ('CHAMBRE', 'Chambre', 'Chambre à coucher', 1, 1),
        ('CUISINE', 'Cuisine', 'Cuisine', 1, 2),
        ('SEJOUR', 'Séjour', 'Séjour / salon', 1, 3),
        ('BUREAU', 'Bureau', 'Bureau / pièce de travail', 1, 4),
        ('SALLE_DE_BAIN', 'Salle de bain', 'Salle de bain', 1, 5),
        ('WC', 'WC', 'Toilettes', 1, 6),
        ('ENTREE', 'Entrée', 'Entrée / hall', 1, 7),
        ('COULOIR', 'Couloir', 'Couloir / circulation', 1, 8)
    """)


def downgrade() -> None:
    op.drop_table("rooms")
    op.drop_table("premises")
    op.drop_table("buildings")
    op.drop_table("sites")
    op.drop_table("room_types")
    op.drop_table("usage_types")
