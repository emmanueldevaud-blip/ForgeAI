"""Update phase tolerances for sechoir-saucisson profile

Revision ID: 20260928_0030
Revises: 20260928_0029
Create Date: 2026-09-28

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260928_0030"
down_revision = "20260928_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update tolerances for all phases of the "sechage-classique" profile
    # Temperature tolerance: 2.0°C, Humidity tolerance: 10.0%
    op.execute("""
        UPDATE domotique_phases
        SET tolerance_temperature = 2.0,
            tolerance_humidity = 10.0
        WHERE profile_id = (
            SELECT id FROM domotique_profiles WHERE code = 'sechage-classique'
        )
    """)


def downgrade() -> None:
    # Revert to original tolerances
    op.execute("""
        UPDATE domotique_phases
        SET tolerance_temperature = CASE
            WHEN name = 'Étuvage' THEN 1.0
            WHEN name = 'Ressuyage' THEN 1.0
            WHEN name = 'Séchage' THEN 1.0
            WHEN name = 'Affinage' THEN 1.0
        END,
        tolerance_humidity = CASE
            WHEN name = 'Étuvage' THEN 3.0
            WHEN name = 'Ressuyage' THEN 3.0
            WHEN name = 'Séchage' THEN 2.0
            WHEN name = 'Affinage' THEN 1.5
        END
        WHERE profile_id = (
            SELECT id FROM domotique_profiles WHERE code = 'sechage-classique'
        )
    """)