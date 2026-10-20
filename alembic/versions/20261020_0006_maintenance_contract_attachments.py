"""Ajoute les pièces jointes aux contrats de maintenance."""

from alembic import op
import sqlalchemy as sa

revision = "20261020_0006"
down_revision = "20261020_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_contract_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["maintenance_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_maintenance_contract_attachments_contract_id"),
        "maintenance_contract_attachments",
        ["contract_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_maintenance_contract_attachments_contract_id"), table_name="maintenance_contract_attachments")
    op.drop_table("maintenance_contract_attachments")