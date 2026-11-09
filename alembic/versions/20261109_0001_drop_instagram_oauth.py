"""Jalon 3 — suppression de l'ancien système OAuth Meta/Instagram.

Drop des tables devenues obsolètes après bascule vers la configuration Meta
centralisée (meta_access_token + instagram_user_id en ModuleConfig) :

- sport_instagram_oauth_states : états d'autorisation OAuth éphémères.
- sport_instagram_connections  : connexions OAuth individuelles par utilisateur.

La configuration Meta centralisée (ModuleConfig, module « administration »)
est l'unique source des jetons de publication.

Revision ID: 20261109_0001
Revises: 20261108_0001
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "20261109_0001"
down_revision = "20261108_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("sport_instagram_oauth_states")
    op.drop_table("sport_instagram_connections")


def downgrade() -> None:
    op.create_table(
        "sport_instagram_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sport_instagram_connections_user_id"), "sport_instagram_connections", ["user_id"], unique=False)
    op.create_index(op.f("ix_sport_instagram_connections_athlete_id"), "sport_instagram_connections", ["athlete_id"], unique=False)
    op.create_index(op.f("ix_sport_instagram_connections_auth_type"), "sport_instagram_connections", ["auth_type"], unique=False)
    op.create_index(op.f("ix_sport_instagram_connections_status"), "sport_instagram_connections", ["status"], unique=False)

    op.create_table(
        "sport_instagram_oauth_states",
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["athlete_id"], ["sport_athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(op.f("ix_sport_instagram_oauth_states_user_id"), "sport_instagram_oauth_states", ["user_id"], unique=False)
    op.create_index(op.f("ix_sport_instagram_oauth_states_athlete_id"), "sport_instagram_oauth_states", ["athlete_id"], unique=False)
