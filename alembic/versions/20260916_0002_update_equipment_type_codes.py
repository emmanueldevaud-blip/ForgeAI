"""update_equipment_type_codes

Revision ID: 20260916_0002
Revises: 20260916_0001
Create Date: 2026-09-16
"""

from alembic import op

revision = "20260916_0002"
down_revision = "20260916_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    code_mapping = [
        ("chauffage", "000001"),
        ("climatisation", "000002"),
        ("ventilation", "000003"),
        ("electricite", "000004"),
        ("plomberie", "000005"),
        ("sanitaire", "000006"),
        ("securite", "000007"),
        ("incendie", "000008"),
        ("eclairage", "000009"),
        ("informatique", "000010"),
        ("equipement_technique", "000011"),
        ("autre", "000012"),
    ]
    for old_code, new_code in code_mapping:
        op.execute(
            f"UPDATE equipment_types SET code = '{new_code}' WHERE code = '{old_code}'"
        )


def downgrade() -> None:
    code_mapping = [
        ("000001", "chauffage"),
        ("000002", "climatisation"),
        ("000003", "ventilation"),
        ("000004", "electricite"),
        ("000005", "plomberie"),
        ("000006", "sanitaire"),
        ("000007", "securite"),
        ("000008", "incendie"),
        ("000009", "eclairage"),
        ("000010", "informatique"),
        ("000011", "equipement_technique"),
        ("000012", "autre"),
    ]
    for old_code, new_code in code_mapping:
        op.execute(
            f"UPDATE equipment_types SET code = '{new_code}' WHERE code = '{old_code}'"
        )
