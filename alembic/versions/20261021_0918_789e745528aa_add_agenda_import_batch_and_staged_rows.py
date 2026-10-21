"""Add agenda import batch and staged rows

Revision ID: 789e745528aa
Revises: 20261020_0006
Create Date: 2026-10-21 09:18:04.201990

"""
from alembic import op
import sqlalchemy as sa

revision = '789e745528aa'
down_revision = '20261020_0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agenda_import_batches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('reference', sa.String(length=64), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='analyzed', nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rows_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rows_ready', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rows_needs_review', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rows_skipped_existing', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rows_excluded', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_count', sa.Integer(), nullable=True),
        sa.Column('week_start', sa.Date(), nullable=True),
        sa.Column('week_end', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference', name='uq_agenda_import_batches_reference'),
    )
    op.create_index(op.f('ix_agenda_import_batches_uploaded_by'), 'agenda_import_batches', ['uploaded_by'], unique=False)

    op.create_table(
        'agenda_import_staged_rows',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('sheet_name', sa.String(length=100), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('presence_date', sa.Date(), nullable=False),
        sa.Column('period', sa.String(length=10), server_default='full', nullable=False),
        sa.Column('is_remote', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('raw_label', sa.String(length=200), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('external_name', sa.String(length=200), nullable=True),
        sa.Column('room_id', sa.Integer(), nullable=True),
        sa.Column('site_label', sa.String(length=50), nullable=True),
        sa.Column('needs_workstation', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('needs_meal', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='ready', nullable=False),
        sa.Column('review_reason', sa.String(length=120), nullable=True),
        sa.Column('suggestions', sa.JSON(), nullable=True),
        sa.Column('created_presence_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['agenda_import_batches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agenda_import_staged_rows_batch_id'), 'agenda_import_staged_rows', ['batch_id'], unique=False)
    op.create_index(op.f('ix_agenda_import_staged_rows_presence_date'), 'agenda_import_staged_rows', ['presence_date'], unique=False)
    op.create_index(op.f('ix_agenda_import_staged_rows_user_id'), 'agenda_import_staged_rows', ['user_id'], unique=False)
    op.create_index(op.f('ix_agenda_import_staged_rows_room_id'), 'agenda_import_staged_rows', ['room_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agenda_import_staged_rows_room_id'), table_name='agenda_import_staged_rows')
    op.drop_index(op.f('ix_agenda_import_staged_rows_user_id'), table_name='agenda_import_staged_rows')
    op.drop_index(op.f('ix_agenda_import_staged_rows_presence_date'), table_name='agenda_import_staged_rows')
    op.drop_index(op.f('ix_agenda_import_staged_rows_batch_id'), table_name='agenda_import_staged_rows')
    op.drop_table('agenda_import_staged_rows')
    op.drop_index(op.f('ix_agenda_import_batches_uploaded_by'), table_name='agenda_import_batches')
    op.drop_table('agenda_import_batches')