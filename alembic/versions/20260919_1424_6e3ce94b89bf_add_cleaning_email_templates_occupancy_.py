"""Add cleaning, email templates, occupancy_occupants association

Revision ID: 6e3ce94b89bf
Revises: ac372105c838
Create Date: 2026-09-19 14:24:45.894250

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '6e3ce94b89bf'
down_revision: Union[str, Sequence[str], None] = 'ac372105c838'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    required_tables = {
        "occupancy_occupants",
        "housing_cleanings",
        "housing_email_templates",
        "housing_email_template_attachments",
        "housing_email_logs",
    }
    if required_tables.issubset(existing_tables):
        return

    # Create occupancy_occupants association table
    op.create_table(
        'occupancy_occupants',
        sa.Column('occupancy_id', sa.Integer(), nullable=False),
        sa.Column('occupant_id', sa.Integer(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['occupancy_id'], ['occupancies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['occupant_id'], ['occupants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('occupancy_id', 'occupant_id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_occupancy_occupants_occupancy', 'occupancy_occupants', ['occupancy_id'])
    op.create_index('ix_occupancy_occupants_occupant', 'occupancy_occupants', ['occupant_id'])

    # Add created_by column to occupancies if not exists (it should already exist)
    # The occupant_id column will be removed in favor of the association table
    # But we keep it for backward compatibility during transition
    # TODO: In a future migration, remove occupant_id from occupancies

    # Create housing_cleanings table
    op.create_table(
        'housing_cleanings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('housing_id', sa.Integer(), nullable=False),
        sa.Column('occupancy_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(length=20), nullable=False, server_default='exit'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='planned'),
        sa.Column('scheduled_date', sa.Date(), nullable=False),
        sa.Column('scheduled_time_start', sa.String(length=5), nullable=True),
        sa.Column('scheduled_time_end', sa.String(length=5), nullable=True),
        sa.Column('actual_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('checklist', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['housing_id'], ['housings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['occupancy_id'], ['occupancies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_cleanings_date_status', 'housing_cleanings', ['scheduled_date', 'status'])
    op.create_index('ix_cleanings_housing_date', 'housing_cleanings', ['housing_id', 'scheduled_date'])
    op.create_index('ix_cleanings_occupancy', 'housing_cleanings', ['occupancy_id'])
    op.create_index('ix_cleanings_assigned', 'housing_cleanings', ['assigned_to'])
    op.create_index('ix_cleanings_status', 'housing_cleanings', ['status'])

    # Create housing_email_templates table
    op.create_table(
        'housing_email_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('template_type', sa.String(length=50), nullable=False),
        sa.Column('subject', sa.String(length=200), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_email_templates_type_active', 'housing_email_templates', ['template_type', 'is_active'])

    # Create housing_email_template_attachments table
    op.create_table(
        'housing_email_template_attachments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['housing_email_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_email_template_attachments_template', 'housing_email_template_attachments', ['template_id'])

    # Create housing_email_logs table
    op.create_table(
        'housing_email_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('occupancy_id', sa.Integer(), nullable=True),
        sa.Column('recipient_email', sa.String(length=200), nullable=False),
        sa.Column('recipient_name', sa.String(length=200), nullable=True),
        sa.Column('subject', sa.String(length=200), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['housing_email_templates.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['occupancy_id'], ['occupancies.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_email_logs_occupancy', 'housing_email_logs', ['occupancy_id'])
    op.create_index('ix_email_logs_status_date', 'housing_email_logs', ['status', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_email_logs_status_date', table_name='housing_email_logs')
    op.drop_index('ix_email_logs_occupancy', table_name='housing_email_logs')
    op.drop_table('housing_email_logs')

    op.drop_index('ix_email_template_attachments_template', table_name='housing_email_template_attachments')
    op.drop_table('housing_email_template_attachments')

    op.drop_index('ix_email_templates_type_active', table_name='housing_email_templates')
    op.drop_table('housing_email_templates')

    op.drop_index('ix_cleanings_status', table_name='housing_cleanings')
    op.drop_index('ix_cleanings_assigned', table_name='housing_cleanings')
    op.drop_index('ix_cleanings_occupancy', table_name='housing_cleanings')
    op.drop_index('ix_cleanings_housing_date', table_name='housing_cleanings')
    op.drop_index('ix_cleanings_date_status', table_name='housing_cleanings')
    op.drop_table('housing_cleanings')

    op.drop_index('ix_occupancy_occupants_occupant', table_name='occupancy_occupants')
    op.drop_index('ix_occupancy_occupants_occupancy', table_name='occupancy_occupants')
    op.drop_table('occupancy_occupants')
