"""Supprime la table sport_instagram_connections (connexions par utilisateur).

Bascule vers l'Instagram Unified Login centralise : le jeton SUAT partage
est stocke une seule fois dans ModuleConfig (meta_access_token), plus de
connexion par utilisateur.

La table sport_instagram_oauth_states (states CSRF) est conservee.
Les cles ModuleConfig instagram_* heritees ne sont pas supprimees (donnees
conservées : elles ne sont plus lues).

Revision ID: 20261111_0001
Revises: 20261110_0001
Create Date: 2026-11-11
"""

import sqlalchemy as sa

from alembic import op

revision = "20261111_0001"
down_revision = "20261110_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("sport_instagram_connections"):
        op.drop_table("sport_instagram_connections")


def downgrade() -> None:
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
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
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
