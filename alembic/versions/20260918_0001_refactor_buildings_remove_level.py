"""Refactor buildings: remove Level, Room.building_id, Room.used_for_accommodation

Revision ID: 20260918_0001
Revises: 20260917_0002
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260918_0001'
down_revision = '20260917_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add building_id column to rooms (nullable initially)
    op.add_column('rooms', sa.Column('building_id', sa.Integer(), nullable=True))

    # Step 2: Add used_for_accommodation column to rooms
    op.add_column('rooms', sa.Column('used_for_accommodation', sa.Boolean(), nullable=False, server_default='0'))

    # Step 3: Migrate data - set building_id from level -> building
    op.execute("""
        UPDATE rooms r
        INNER JOIN levels l ON r.level_id = l.id
        SET r.building_id = l.building_id
    """)

    # Step 4: Make building_id NOT NULL using raw SQL (MySQL requires type)
    op.execute("ALTER TABLE rooms MODIFY COLUMN building_id INTEGER NOT NULL")

    # Step 5: Drop level_id from rooms
    op.execute("ALTER TABLE rooms DROP FOREIGN KEY fk_rooms_level_id")
    op.drop_index('ix_rooms_level_active', table_name='rooms')
    op.execute("ALTER TABLE rooms DROP INDEX uq_room_level_reference")
    op.drop_column('rooms', 'level_id')

    # Step 6: Add new constraints for building_id
    op.create_unique_constraint('uq_room_building_reference', 'rooms', ['building_id', 'reference'])
    op.create_index('ix_rooms_building_active', 'rooms', ['building_id', 'is_active'])

    # Step 7: Drop levels table
    op.drop_table('levels')


def downgrade() -> None:
    # Recreate levels table
    op.create_table(
        'levels',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('building_id', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('level_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['building_id'], ['buildings.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('building_id', 'reference', name='uq_level_building_reference'),
    )
    op.create_index('ix_levels_building_active', 'levels', ['building_id', 'is_active'])

    # Add level_id back to rooms
    op.add_column('rooms', sa.Column('level_id', sa.Integer(), nullable=True))

    # Migrate data - for each room, find its level based on building_id
    op.execute("""
        UPDATE rooms r
        INNER JOIN levels l ON r.building_id = l.building_id
        SET r.level_id = l.id
    """)

    op.execute("ALTER TABLE rooms MODIFY COLUMN level_id INTEGER NOT NULL")

    # Drop building_id constraints
    op.drop_constraint('uq_room_building_reference', 'rooms', type_='unique')
    op.drop_index('ix_rooms_building_active', table_name='rooms')
    op.drop_column('rooms', 'building_id')
    op.drop_column('rooms', 'used_for_accommodation')

    # Recreate level_id constraints
    op.create_unique_constraint('uq_room_level_reference', 'rooms', ['level_id', 'reference'])
    op.create_index('ix_rooms_level_active', 'rooms', ['level_id', 'is_active'])
    op.create_foreign_key('fk_rooms_level_id', 'rooms', 'levels', ['level_id'], ['id'], ondelete='CASCADE')
