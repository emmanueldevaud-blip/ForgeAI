"""it asset v2 inventory fields

Revision ID: 202610100215_it_asset_v2
Revises: 202610091040_it_asset
Create Date: 2026-10-10 02:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '202610100215_it_asset_v2'
down_revision: Union[str, Sequence[str], None] = '202610091040_it_asset'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Colonnes ajoutées, dans l'ordre inverse pour le downgrade.
_COLUMNS = [
    ('os_build', sa.String(length=50)),
    ('os_architecture', sa.String(length=20)),
    ('cpu_name', sa.String(length=200)),
    ('cpu_cores', sa.Integer()),
    ('ram_total_mb', sa.Integer()),
    ('ram_free_mb', sa.Integer()),
    ('disk_total_mb', sa.Integer()),
    ('disk_free_mb', sa.Integer()),
    ('bios_version', sa.String(length=100)),
    ('manufacturer_system', sa.String(length=200)),
    ('last_collection', sa.DateTime(timezone=True)),
    ('agent_version', sa.String(length=20)),
    ('domain', sa.String(length=200)),
    ('computer_name_ad', sa.String(length=200)),
    ('organizational_unit', sa.String(length=500)),
    ('last_ad_activity', sa.DateTime(timezone=True)),
    ('is_domain_joined', sa.Boolean()),
    ('domain_last_sync', sa.DateTime(timezone=True)),
    ('snmp_manufacturer', sa.String(length=200)),
    ('snmp_model', sa.String(length=200)),
    ('snmp_firmware_version', sa.String(length=100)),
    ('snmp_contact', sa.String(length=200)),
    ('snmp_location', sa.String(length=500)),
]


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column('it_assets', sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column('it_assets', name)
