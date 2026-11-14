"""Tables Meta Analytics & Intelligence (Community Manager IA).

Tables additives uniquement : aucune table ni colonne existante n'est modifiee.
Historisation des metriques Instagram/Facebook, comptes, medias, audience,
traces de synchronisation, analyses IA et recommandations editoriales.

Revision ID: 20261114_0001_meta_analytics
Revises: 20261113_0001
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "20261114_0001_meta_analytics"
down_revision = "20261113_0001"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(name)


def upgrade() -> None:
    if not _table_exists("meta_analytics_accounts"):
        op.create_table(
            "meta_analytics_accounts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column("platform_account_id", sa.String(length=100), nullable=False),
            sa.Column("account_name", sa.String(length=200), nullable=True),
            sa.Column("username", sa.String(length=150), nullable=True),
            sa.Column("account_type", sa.String(length=50), nullable=True),
            sa.Column("business_portfolio_id", sa.String(length=100), nullable=True),
            sa.Column("page_id", sa.String(length=100), nullable=True),
            sa.Column("instagram_account_id", sa.String(length=100), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index(
            "uq_meta_analytics_account_platform",
            "meta_analytics_accounts",
            ["platform", "platform_account_id"],
            unique=True,
        )
        op.create_index("ix_meta_analytics_accounts_platform", "meta_analytics_accounts", ["platform"])
        op.create_index("ix_meta_analytics_accounts_active", "meta_analytics_accounts", ["is_active"])

    if not _table_exists("meta_analytics_media"):
        op.create_table(
            "meta_analytics_media",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("media_id", sa.String(length=100), nullable=False),
            sa.Column("media_type", sa.String(length=30), nullable=True),
            sa.Column("media_url", sa.Text(), nullable=True),
            sa.Column("permalink", sa.Text(), nullable=True),
            sa.Column("caption", sa.Text(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["meta_analytics_accounts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index(
            "uq_meta_analytics_media_account_media",
            "meta_analytics_media",
            ["account_id", "media_id"],
            unique=True,
        )
        op.create_index("ix_meta_analytics_media_account", "meta_analytics_media", ["account_id"])
        op.create_index("ix_meta_analytics_media_type", "meta_analytics_media", ["media_type"])

    if not _table_exists("meta_analytics_snapshots"):
        op.create_table(
            "meta_analytics_snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("media_id", sa.Integer(), nullable=True),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column("metric_name", sa.String(length=100), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=True),
            sa.Column("metric_status", sa.String(length=30), nullable=False, server_default=sa.text("'available'")),
            sa.Column("period", sa.String(length=30), nullable=True),
            sa.Column("period_start", sa.Date(), nullable=True),
            sa.Column("period_end", sa.Date(), nullable=True),
            sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("api_version", sa.String(length=20), nullable=True),
            sa.Column("source_api", sa.String(length=100), nullable=True),
            sa.ForeignKeyConstraint(["account_id"], ["meta_analytics_accounts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["media_id"], ["meta_analytics_media.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index(
            "ix_meta_analytics_snapshots_account_metric",
            "meta_analytics_snapshots",
            ["account_id", "metric_name", "collected_at"],
        )
        op.create_index("ix_meta_analytics_snapshots_media", "meta_analytics_snapshots", ["media_id", "metric_name"])
        op.create_index("ix_meta_analytics_snapshots_period", "meta_analytics_snapshots", ["period_start", "period_end"])

    if not _table_exists("meta_analytics_account_metrics"):
        op.create_table(
            "meta_analytics_account_metrics",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("metric_name", sa.String(length=100), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=True),
            sa.Column("metric_status", sa.String(length=30), nullable=False, server_default=sa.text("'available'")),
            sa.Column("period", sa.String(length=30), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["meta_analytics_accounts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index(
            "uq_meta_analytics_account_metrics",
            "meta_analytics_account_metrics",
            ["account_id", "metric_name", "period"],
            unique=True,
        )

    if not _table_exists("meta_analytics_audience"):
        op.create_table(
            "meta_analytics_audience",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("dimension", sa.String(length=30), nullable=False),
            sa.Column("dimension_value", sa.String(length=150), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=True),
            sa.Column("metric_status", sa.String(length=30), nullable=False, server_default=sa.text("'available'")),
            sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["meta_analytics_accounts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("ix_meta_analytics_audience_account_dim", "meta_analytics_audience", ["account_id", "dimension"])

    if not _table_exists("meta_analytics_sync_runs"):
        op.create_table(
            "meta_analytics_sync_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("accounts_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("metrics_collected", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["account_id"], ["meta_analytics_accounts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index(
            "ix_meta_analytics_sync_runs_platform_status",
            "meta_analytics_sync_runs",
            ["platform", "status", "started_at"],
        )

    if not _table_exists("meta_analytics_ai_analyses"):
        op.create_table(
            "meta_analytics_ai_analyses",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("analysis_type", sa.String(length=50), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("findings_json", sa.JSON(), nullable=True),
            sa.Column("confidence", sa.String(length=30), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("ix_meta_analytics_ai_analyses_period", "meta_analytics_ai_analyses", ["period_start", "period_end"])

    if not _table_exists("meta_analytics_recommendations"):
        op.create_table(
            "meta_analytics_recommendations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("analysis_id", sa.Integer(), nullable=True),
            sa.Column("recommendation_type", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("indicators_json", sa.JSON(), nullable=True),
            sa.Column("confidence", sa.String(length=30), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("action", sa.String(length=50), nullable=True),
            sa.Column("linked_entry_id", sa.Integer(), nullable=True),
            sa.Column("linked_publication_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["analysis_id"], ["meta_analytics_ai_analyses.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["linked_entry_id"], ["editorial_calendar_entries.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["linked_publication_id"], ["sport_publications.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        op.create_index("ix_meta_analytics_recommendations_status", "meta_analytics_recommendations", ["status"])
        op.create_index("ix_meta_analytics_recommendations_created", "meta_analytics_recommendations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_meta_analytics_recommendations_created", table_name="meta_analytics_recommendations")
    op.drop_index("ix_meta_analytics_recommendations_status", table_name="meta_analytics_recommendations")
    op.drop_table("meta_analytics_recommendations")
    op.drop_index("ix_meta_analytics_ai_analyses_period", table_name="meta_analytics_ai_analyses")
    op.drop_table("meta_analytics_ai_analyses")
    op.drop_index("ix_meta_analytics_sync_runs_platform_status", table_name="meta_analytics_sync_runs")
    op.drop_table("meta_analytics_sync_runs")
    op.drop_index("ix_meta_analytics_audience_account_dim", table_name="meta_analytics_audience")
    op.drop_table("meta_analytics_audience")
    op.drop_index("uq_meta_analytics_account_metrics", table_name="meta_analytics_account_metrics")
    op.drop_table("meta_analytics_account_metrics")
    op.drop_index("ix_meta_analytics_snapshots_period", table_name="meta_analytics_snapshots")
    op.drop_index("ix_meta_analytics_snapshots_media", table_name="meta_analytics_snapshots")
    op.drop_index("ix_meta_analytics_snapshots_account_metric", table_name="meta_analytics_snapshots")
    op.drop_table("meta_analytics_snapshots")
    op.drop_index("ix_meta_analytics_media_type", table_name="meta_analytics_media")
    op.drop_index("ix_meta_analytics_media_account", table_name="meta_analytics_media")
    op.drop_index("uq_meta_analytics_media_account_media", table_name="meta_analytics_media")
    op.drop_table("meta_analytics_media")
    op.drop_index("ix_meta_analytics_accounts_active", table_name="meta_analytics_accounts")
    op.drop_index("ix_meta_analytics_accounts_platform", table_name="meta_analytics_accounts")
    op.drop_index("uq_meta_analytics_account_platform", table_name="meta_analytics_accounts")
    op.drop_table("meta_analytics_accounts")
