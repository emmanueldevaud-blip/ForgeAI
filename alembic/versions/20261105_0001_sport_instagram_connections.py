"""Add SportInstagramConnection table for Meta Instagram Insights."""
from alembic import op
import sqlalchemy as sa

revision = "20261105_0001"
down_revision = "20261104_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("sport_instagram_connections"):
        return
    op.create_table(
        "sport_instagram_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instagram_business_account_id", sa.String(255), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_long_lived_token", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("scopes", sa.String(255), nullable=True),
        sa.Column("token_type", sa.String(50), nullable=True),
        sa.Column("expires_in", sa.Integer(), nullable=True),
        sa.Column("obtained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sport_instagram_connections_user_id", "sport_instagram_connections", ["user_id"])
    op.create_index("ix_sport_instagram_connections_athlete_id", "sport_instagram_connections", ["athlete_id"])
    op.create_index("ix_sport_instagram_connections_status", "sport_instagram_connections", ["status"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("sport_instagram_connections"):
        return
    op.drop_table("sport_instagram_connections")
