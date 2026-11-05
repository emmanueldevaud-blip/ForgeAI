"""add sport instagram oauth states

Revision ID: 20261105_0002
Revises: 20261105_0001
Create Date: 2026-11-05 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261105_0002"
down_revision = "20261105_0001"
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import text
    conn = op.get_bind()
    conn.execute(text("CREATE TABLE IF NOT EXISTS sport_instagram_oauth_states (state VARCHAR(128) PRIMARY KEY, user_id INTEGER NOT NULL, athlete_id INTEGER NOT NULL, expires_at DATETIME NOT NULL, consumed BOOLEAN NOT NULL DEFAULT FALSE, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY (athlete_id) REFERENCES sport_athletes(id) ON DELETE CASCADE)"))
    ret
