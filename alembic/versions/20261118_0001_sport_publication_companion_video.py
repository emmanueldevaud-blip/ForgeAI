"""Ajoute les champs média vidéo musical complémentaire aux publications sportives.

Revision ID: 20261118_0001_sp_companion_video
Revises: 20261117_0001_cm_strategy
Create Date: 2026-11-18
"""

import sqlalchemy as sa

from alembic import op

revision = "20261118_0001_sp_companion_video"
down_revision = "20261117_0001_cm_strategy"
branch_labels = None
depends_on = None


def _columns_exist() -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns("sport_publications")}


def _indexes_exist() -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {idx["name"] for idx in insp.get_indexes("sport_publications")}


def upgrade() -> None:
    existing = _columns_exist()
    if "companion_video_status" not in existing:
        op.add_column(
            "sport_publications",
            sa.Column("companion_video_status", sa.String(length=30), nullable=False, server_default="none"),
        )
    if "companion_video_job_id" not in existing:
        op.add_column(
            "sport_publications",
            sa.Column("companion_video_job_id", sa.String(length=36), nullable=True),
        )
    if "companion_video_path" not in existing:
        op.add_column(
            "sport_publications",
            sa.Column("companion_video_path", sa.String(length=500), nullable=True),
        )
    if "companion_video_error" not in existing:
        op.add_column(
            "sport_publications",
            sa.Column("companion_video_error", sa.Text(), nullable=True),
        )
    if "companion_video_generated_at" not in existing:
        op.add_column(
            "sport_publications",
            sa.Column("companion_video_generated_at", sa.DateTime(timezone=True), nullable=True),
        )
    indexes = _indexes_exist()
    if "ix_sport_publications_companion_video_status" not in indexes:
        op.create_index(
            "ix_sport_publications_companion_video_status",
            "sport_publications",
            ["companion_video_status"],
            unique=False,
        )


def downgrade() -> None:
    indexes = _indexes_exist()
    if "ix_sport_publications_companion_video_status" in indexes:
        op.drop_index("ix_sport_publications_companion_video_status", table_name="sport_publications")
    existing = _columns_exist()
    for column in (
        "companion_video_generated_at",
        "companion_video_error",
        "companion_video_path",
        "companion_video_job_id",
        "companion_video_status",
    ):
        if column in existing:
            op.drop_column("sport_publications", column)
