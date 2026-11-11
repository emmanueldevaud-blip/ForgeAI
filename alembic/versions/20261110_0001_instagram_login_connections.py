"""Recrée les tables Instagram Login (connexions par utilisateur + states CSRF).

Suite de la bascule vers Instagram Login individuel (voie B) :
- sport_instagram_connections : une connexion active par utilisateur
  (sans athlete_id, user_id unique).
- sport_instagram_oauth_states : states OAuth CSRF éphémères (10 minutes).

Revision ID: 20261110_0001
Revises: 20261109_0003
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op

revision = "20261110_0001"
down_revision = "20261109_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    if not insp.has_table("sport_instagram_connections"):
        op.create_table(
            "sport_instagram_connections",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("instagram_business_account_id", sa.String(length=255), nullable=True),
            sa.Column("auth_type", sa.String(length=30), nullable=False),
            sa.Column("encrypted_access_token", sa.Text(), nullable=True),
            sa.Column("encrypted_long_lived_token", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("scopes", sa.String(length=255), nullable=True),
            sa.Column("token_type", sa.String(length=50), nullable=True),
            sa.Column("expires_in", sa.Integer(), nullable=True),
            sa.Column("obtained_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_sport_instagram_connections_user_id"),
            "sport_instagram_connections",
            ["user_id"],
            unique=True,
        )
        op.create_index(
            op.f("ix_sport_instagram_connections_status"),
            "sport_instagram_connections",
            ["status"],
            unique=False,
        )

    if not insp.has_table("sport_instagram_oauth_states"):
        op.create_table(
            "sport_instagram_oauth_states",
            sa.Column("state", sa.String(length=128), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("state"),
        )
        op.create_index(
            op.f("ix_sport_instagram_oauth_states_user_id"),
            "sport_instagram_oauth_states",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_sport_instagram_oauth_states_expires_at"),
            "sport_instagram_oauth_states",
            ["expires_at"],
            unique=False,
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("sport_instagram_oauth_states"):
        op.drop_table("sport_instagram_oauth_states")
    if insp.has_table("sport_instagram_connections"):
        op.drop_table("sport_instagram_connections")
