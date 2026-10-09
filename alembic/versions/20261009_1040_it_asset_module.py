"""add it_asset module

Revision ID: 202610091040_it_asset
Revises: ba51ae6eea49
Create Date: 2026-10-09 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '202610091040_it_asset'
down_revision: Union[str, Sequence[str], None] = 'ba51ae6eea49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # it_assets
    op.create_table(
        'it_assets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('reference', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('asset_type', sa.String(length=20), nullable=False),
        sa.Column('manufacturer', sa.String(length=200), nullable=True),
        sa.Column('model', sa.String(length=200), nullable=True),
        sa.Column('serial_number', sa.String(length=200), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('mac_address', sa.String(length=17), nullable=True),
        sa.Column('os', sa.String(length=100), nullable=True),
        sa.Column('os_version', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('discovery_source', sa.String(length=20), nullable=False),
        sa.Column('discovery_data', sa.JSON(), nullable=True),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('meshcentral_id', sa.String(length=100), nullable=True),
        sa.Column('wol_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('wol_mac', sa.String(length=17), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_check', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], name=op.f('it_assets_ibfk_1'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    with op.batch_alter_table('it_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_it_assets_ip_active'), ['ip_address', 'is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_it_assets_mac_active'), ['mac_address', 'is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_it_assets_reference'), ['reference'], unique=True)
        batch_op.create_index(batch_op.f('ix_it_assets_room_active'), ['room_id', 'is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_it_assets_serial_number'), ['serial_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_it_assets_status_active'), ['status', 'is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_it_assets_type_active'), ['asset_type', 'is_active'], unique=False)
        batch_op.create_index('ix_it_assets_meshcentral_id', ['meshcentral_id'], unique=True)

    # it_network_ranges
    op.create_table(
        'it_network_ranges',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('cidr', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('vlan_id', sa.Integer(), nullable=True),
        sa.Column('site_id', sa.Integer(), nullable=True),
        sa.Column('scan_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('scan_interval_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('snmp_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('snmp_community', sa.String(length=100), nullable=True),
        sa.Column('snmp_version', sa.String(length=20), nullable=True),
        sa.Column('snmp_port', sa.Integer(), nullable=False, server_default='161'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_scan_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_scan_status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], name=op.f('it_network_ranges_ibfk_1'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    with op.batch_alter_table('it_network_ranges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_it_network_ranges_cidr'), ['cidr'], unique=True)
        batch_op.create_index(batch_op.f('ix_it_network_ranges_site_active'), ['site_id', 'is_active'], unique=False)

    # it_discovery_logs
    op.create_table(
        'it_discovery_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('network_range_id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='running'),
        sa.Column('hosts_scanned', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('hosts_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('assets_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('assets_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['network_range_id'], ['it_network_ranges.id'], name=op.f('it_discovery_logs_ibfk_1'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    with op.batch_alter_table('it_discovery_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_it_discovery_logs_range_started'), ['network_range_id', 'started_at'], unique=False)

    # it_asset_observations
    op.create_table(
        'it_asset_observations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('check_method', sa.String(length=50), nullable=False, server_default='ping'),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['it_assets.id'], name=op.f('it_asset_observations_ibfk_1'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    with op.batch_alter_table('it_asset_observations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_it_asset_observations_asset_checked'), ['asset_id', 'checked_at'], unique=False)

    # it_alerts
    op.create_table(
        'it_alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=30), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='info'),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('acknowledged', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('acknowledged_by', sa.Integer(), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.ForeignKeyConstraint(['acknowledged_by'], ['users.id'], name=op.f('it_alerts_ibfk_1'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['asset_id'], ['it_assets.id'], name=op.f('it_alerts_ibfk_2'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    with op.batch_alter_table('it_alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_it_alerts_asset_resolved'), ['asset_id', 'resolved'], unique=False)
        batch_op.create_index(batch_op.f('ix_it_alerts_severity_created'), ['severity', 'created_at'], unique=False)

    # it_asset_history
    op.create_table(
        'it_asset_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('field_name', sa.String(length=100), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('change_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(now())'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['it_assets.id'], name=op.f('it_asset_history_ibfk_1'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], name=op.f('it_asset_history_ibfk_2'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )
    with op.batch_alter_table('it_asset_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_it_asset_history_asset_created'), ['asset_id', 'created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('it_asset_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_it_asset_history_asset_created'))
    op.drop_table('it_asset_history')

    with op.batch_alter_table('it_alerts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_it_alerts_severity_created'))
        batch_op.drop_index(batch_op.f('ix_it_alerts_asset_resolved'))
    op.drop_table('it_alerts')

    with op.batch_alter_table('it_asset_observations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_it_asset_observations_asset_checked'))
    op.drop_table('it_asset_observations')

    with op.batch_alter_table('it_discovery_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_it_discovery_logs_range_started'))
    op.drop_table('it_discovery_logs')

    with op.batch_alter_table('it_network_ranges', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_it_network_ranges_site_active'))
        batch_op.drop_index(batch_op.f('ix_it_network_ranges_cidr'))
    op.drop_table('it_network_ranges')

    with op.batch_alter_table('it_assets', schema=None) as batch_op:
        batch_op.drop_index('ix_it_assets_meshcentral_id')
        batch_op.drop_index(batch_op.f('ix_it_assets_type_active'))
        batch_op.drop_index(batch_op.f('ix_it_assets_status_active'))
        batch_op.drop_index(batch_op.f('ix_it_assets_serial_number'))
        batch_op.drop_index(batch_op.f('ix_it_assets_room_active'))
        batch_op.drop_index(batch_op.f('ix_it_assets_reference'))
        batch_op.drop_index(batch_op.f('ix_it_assets_mac_active'))
        batch_op.drop_index(batch_op.f('ix_it_assets_ip_active'))
    op.drop_table('it_assets')