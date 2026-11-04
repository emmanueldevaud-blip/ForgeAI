"""Add SportPublication table for Instagram publications."""
from alembic import op
import sqlalchemy as sa

revision = "20261104_0002"
down_revision = "20261104_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("sport_publications"):
        return
    op.create_table(
        "sport_publications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("sport_activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("styles", sa.JSON(), nullable=False),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column("proposals", sa.JSON(), nullable=False),
        sa.Column("selected_proposal", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("photo_id", sa.Integer(), sa.ForeignKey("photos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visual_type", sa.String(30), nullable=False, server_default="photo"),
        sa.Column("card_path", sa.String(500), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", name="uq_sport_publication_activity"),
    )
    op.create_index("ix_sport_publications_athlete_status", "sport_publications", ["athlete_id", "status"])
    op.create_index("ix_sport_publications_activity", "sport_publications", ["activity_id"])


def downgrade() -> None:
    op.drop_index("ix_sport_publications_activity", table_name="sport_publications")
    op.drop_index("ix_sport_publications_athlete_status", table_name="sport_publications")
    op.drop_table("sport_publications")