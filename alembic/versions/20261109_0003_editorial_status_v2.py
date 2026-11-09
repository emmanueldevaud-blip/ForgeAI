"""extend ck_status_valid with suggestion statuses

Revision ID: 20261109_0003
Revises: 20261109_0002
Create Date: 2026-11-09 09:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20261109_0003'
down_revision: Union[str, Sequence[str], None] = '20261109_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_STATUS_CHECK = (
    "status IN ("
    "'brouillon','planifié','publié','refusé',"
    "'pending','accepted','refused'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_status_valid",
        "editorial_calendar_entries",
        type_="check",
    )
    op.create_check_constraint(
        "ck_status_valid",
        "editorial_calendar_entries",
        NEW_STATUS_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_status_valid",
        "editorial_calendar_entries",
        type_="check",
    )
    op.create_check_constraint(
        "ck_status_valid",
        "editorial_calendar_entries",
        "status IN ('brouillon','planifié','publié','refusé')",
    )
