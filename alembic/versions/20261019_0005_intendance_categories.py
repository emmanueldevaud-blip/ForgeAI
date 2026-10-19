"""Ajoute le référentiel des catégories Intendance."""

from alembic import op
import sqlalchemy as sa

revision = "20261019_0005"
down_revision = "20261019_0004"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "intendance_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("excluded_from_dashboard", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name"),
    )
    bind = op.get_bind()
    bind.execute(sa.text("INSERT IGNORE INTO intendance_categories (name) SELECT DISTINCT category FROM intendance_account_codes WHERE category IS NOT NULL AND TRIM(category) <> ''"))

def downgrade():
    op.drop_table("intendance_categories")
