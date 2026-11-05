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
    return
        "sport_instagram_oauth_states",
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index("ix_sport_instagram_oauth_states_user_id", "sport_instagram_oauth_states", ["user_id"])
    op.create_index("ix_sport_instagram_oauth_states_athlete_id", "sport_instagram_oauth_states", ["athlete_id"])


def downgrade():
    op.drop_table("sport_instagram_oauth_states")
