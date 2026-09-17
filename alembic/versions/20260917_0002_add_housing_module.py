"""add_housing_module

Revision ID: 20260917_0002
Revises: 20260917_0001
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260917_0002'
down_revision: Union[str, None] = '20260917_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'housings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('housing_type', sa.String(50), nullable=True),
        sa.Column('capacity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('beds', sa.Integer(), nullable=True),
        sa.Column('bathrooms', sa.Integer(), nullable=True),
        sa.Column('has_kitchen', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('has_balcony', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('floor_number', sa.String(20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('room_id'),
    )
    op.create_index('ix_housings_active', 'housings', ['is_active'])

    op.create_table(
        'occupants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('id_type', sa.String(50), nullable=True),
        sa.Column('id_number', sa.String(100), nullable=True),
        sa.Column('company', sa.String(200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_occupants_name', 'occupants', ['last_name', 'first_name'])

    op.create_table(
        'occupancies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('housing_id', sa.Integer(), nullable=False),
        sa.Column('occupant_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(30), server_default='pre_reserved', nullable=False),
        sa.Column('arrival_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('departure_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actual_arrival', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_departure', sa.DateTime(timezone=True), nullable=True),
        sa.Column('purpose', sa.String(200), nullable=True),
        sa.Column('observations', sa.Text(), nullable=True),
        sa.Column('nb_persons', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['housing_id'], ['housings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['occupant_id'], ['occupants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_occupancies_housing', 'occupancies', ['housing_id'])
    op.create_index('ix_occupancies_occupant', 'occupancies', ['occupant_id'])
    op.create_index('ix_occupancies_status', 'occupancies', ['status'])
    op.create_index('ix_occupancies_dates', 'occupancies', ['arrival_date', 'departure_date'])

    op.create_table(
        'housing_unavailabilities',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('housing_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(50), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['housing_id'], ['housings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_housing_unavail_housing', 'housing_unavailabilities', ['housing_id'])
    op.create_index('ix_housing_unavail_dates', 'housing_unavailabilities', ['start_date', 'end_date'])

    op.create_table(
        'housing_status_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('housing_id', sa.Integer(), nullable=False),
        sa.Column('field_name', sa.String(50), nullable=False),
        sa.Column('old_value', sa.String(100), nullable=True),
        sa.Column('new_value', sa.String(100), nullable=True),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['housing_id'], ['housings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_housing_status_history_housing', 'housing_status_history', ['housing_id', 'changed_at'])

    op.create_table(
        'occupancy_status_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('occupancy_id', sa.Integer(), nullable=False),
        sa.Column('old_status', sa.String(30), nullable=True),
        sa.Column('new_status', sa.String(30), nullable=False),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['occupancy_id'], ['occupancies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_occupancy_status_history_occupancy', 'occupancy_status_history', ['occupancy_id', 'changed_at'])


def downgrade() -> None:
    op.drop_table('occupancy_status_history')
    op.drop_table('housing_status_history')
    op.drop_table('housing_unavailabilities')
    op.drop_table('occupancies')
    op.drop_table('occupants')
    op.drop_table('housings')
