"""Add RBAC, Module system, Audit log, AD integration models

Revision ID: 1b9654c0c3d3
Revises: 001_initial
Create Date: 2026-08-27 19:47:45.869612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b9654c0c3d3'
down_revision: Union[str, Sequence[str], None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### RBAC tables ###

    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_roles_code', 'roles', ['code'], unique=True)
    op.create_index('ix_roles_code_active', 'roles', ['code', 'is_active'])

    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(100), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('module', sa.String(50), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_permissions_code', 'permissions', ['code'], unique=True)
    op.create_index('ix_permissions_module_code', 'permissions', ['module', 'code'])

    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('ad_dn', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_groups_code', 'groups', ['code'], unique=True)
    op.create_index('ix_groups_ad_dn', 'groups', ['ad_dn'], unique=True)
    op.create_index('ix_groups_code_active', 'groups', ['code', 'is_active'])

    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('assigned_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('user_id', 'role_id'),
    )
    op.create_index('ix_user_roles_user_id', 'user_roles', ['user_id'])
    op.create_index('ix_user_roles_role_id', 'user_roles', ['role_id'])

    op.create_table(
        'group_roles',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'role_id'),
    )
    op.create_index('ix_group_roles_group_id', 'group_roles', ['group_id'])
    op.create_index('ix_group_roles_role_id', 'group_roles', ['role_id'])

    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
    )

    op.create_table(
        'user_groups',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'group_id'),
    )
    op.create_index('ix_user_groups_user_id', 'user_groups', ['user_id'])
    op.create_index('ix_user_groups_group_id', 'user_groups', ['group_id'])

    # ### Module tables ###

    op.create_table(
        'modules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(100), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='inactive'),
        sa.Column('version', sa.String(20), nullable=False, server_default='1.0.0'),
        sa.Column('route_path', sa.String(200), nullable=True),
        sa.Column('component_path', sa.String(200), nullable=True),
        sa.Column('required_permissions', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('settings', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('is_core', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('dependencies', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_modules_code', 'modules', ['code'], unique=True)
    op.create_index('ix_modules_code_status', 'modules', ['code', 'status'])
    op.create_index('ix_modules_order', 'modules', ['order'])

    op.create_table(
        'module_configs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('module_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('value_type', sa.String(20), nullable=False, server_default='string'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_secret', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('validation', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['module_id'], ['modules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_module_configs_module_id', 'module_configs', ['module_id'])
    op.create_index('ix_module_configs_module_key', 'module_configs', ['module_id', 'key'], unique=True)

    # ### Audit log table ###

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('module', sa.String(50), nullable=False),
        sa.Column('object_type', sa.String(100), nullable=True),
        sa.Column('object_id', sa.String(100), nullable=True),
        sa.Column('object_repr', sa.String(500), nullable=True),
        sa.Column('old_values', sa.JSON(), nullable=True),
        sa.Column('new_values', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='success'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_username', 'audit_logs', ['username'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_module', 'audit_logs', ['module'])
    op.create_index('ix_audit_logs_object_type', 'audit_logs', ['object_type'])
    op.create_index('ix_audit_logs_object_id', 'audit_logs', ['object_id'])
    op.create_index('ix_audit_logs_request_id', 'audit_logs', ['request_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_logs_user_module_created', 'audit_logs', ['user_id', 'module', 'created_at'])
    op.create_index('ix_audit_logs_module_action_created', 'audit_logs', ['module', 'action', 'created_at'])
    op.create_index('ix_audit_logs_object', 'audit_logs', ['object_type', 'object_id'])

    # ### AD integration tables ###

    op.create_table(
        'ad_configs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('server', sa.String(255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False, server_default='636'),
        sa.Column('use_ssl', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('base_dn', sa.String(500), nullable=False),
        sa.Column('user_dn', sa.String(500), nullable=True),
        sa.Column('user_search_filter', sa.String(255), nullable=False, server_default='(sAMAccountName={username})'),
        sa.Column('group_search_base', sa.String(500), nullable=True),
        sa.Column('bind_user', sa.String(255), nullable=False),
        sa.Column('bind_password', sa.String(255), nullable=False),
        sa.Column('connect_timeout', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('receive_timeout', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('page_size', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('follow_referrals', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_status', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ad_configs_name', 'ad_configs', ['name'], unique=True)
    op.create_index('ix_ad_configs_active', 'ad_configs', ['is_active'])

    op.create_table(
        'ad_group_mappings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ad_config_id', sa.Integer(), nullable=False),
        sa.Column('ad_group_cn', sa.String(255), nullable=False),
        sa.Column('ad_group_dn', sa.String(500), nullable=True),
        sa.Column('role_code', sa.String(50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['ad_config_id'], ['ad_configs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ad_group_mappings_ad_config_id', 'ad_group_mappings', ['ad_config_id'])
    op.create_index('ix_ad_group_mappings_role_code', 'ad_group_mappings', ['role_code'])
    op.create_index('ix_ad_group_mappings_unique', 'ad_group_mappings', ['ad_config_id', 'ad_group_cn'], unique=True)

    op.create_table(
        'ad_sync_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ad_config_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('users_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('users_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('users_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('users_deactivated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('groups_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('groups_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('groups_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('triggered_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['ad_config_id'], ['ad_configs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['triggered_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ad_sync_logs_ad_config_id', 'ad_sync_logs', ['ad_config_id'])
    op.create_index('ix_ad_sync_logs_config_started', 'ad_sync_logs', ['ad_config_id', 'started_at'])

    # ### Update users table - fix ad_dn unique constraint ###
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index(op.f('ix_users_ad_dn'))
        batch_op.create_unique_constraint('uq_users_ad_dn', ['ad_dn'])


def downgrade() -> None:
    # ### Update users table - revert ad_dn unique constraint ###
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('uq_users_ad_dn', type_='unique')
        batch_op.create_index(op.f('ix_users_ad_dn'), ['ad_dn'], unique=True)

    # ### Drop AD integration tables ###
    op.drop_index('ix_ad_sync_logs_config_started', table_name='ad_sync_logs')
    op.drop_index('ix_ad_sync_logs_ad_config_id', table_name='ad_sync_logs')
    op.drop_table('ad_sync_logs')

    op.drop_index('ix_ad_group_mappings_unique', table_name='ad_group_mappings')
    op.drop_index('ix_ad_group_mappings_role_code', table_name='ad_group_mappings')
    op.drop_index('ix_ad_group_mappings_ad_config_id', table_name='ad_group_mappings')
    op.drop_table('ad_group_mappings')

    op.drop_index('ix_ad_configs_active', table_name='ad_configs')
    op.drop_index('ix_ad_configs_name', table_name='ad_configs')
    op.drop_table('ad_configs')

    # ### Drop audit log table ###
    op.drop_index('ix_audit_logs_object', table_name='audit_logs')
    op.drop_index('ix_audit_logs_module_action_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_module_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_request_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_object_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_object_type', table_name='audit_logs')
    op.drop_index('ix_audit_logs_module', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_username', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_table('audit_logs')

    # ### Drop module tables ###
    op.drop_index('ix_module_configs_module_key', table_name='module_configs')
    op.drop_index('ix_module_configs_module_id', table_name='module_configs')
    op.drop_table('module_configs')

    op.drop_index('ix_modules_order', table_name='modules')
    op.drop_index('ix_modules_code_status', table_name='modules')
    op.drop_index('ix_modules_code', table_name='modules')
    op.drop_table('modules')

    # ### Drop RBAC tables ###
    op.drop_index('ix_user_groups_group_id', table_name='user_groups')
    op.drop_index('ix_user_groups_user_id', table_name='user_groups')
    op.drop_table('user_groups')

    op.drop_table('role_permissions')

    op.drop_index('ix_group_roles_role_id', table_name='group_roles')
    op.drop_index('ix_group_roles_group_id', table_name='group_roles')
    op.drop_table('group_roles')

    op.drop_index('ix_user_roles_role_id', table_name='user_roles')
    op.drop_index('ix_user_roles_user_id', table_name='user_roles')
    op.drop_table('user_roles')

    op.drop_index('ix_groups_code_active', table_name='groups')
    op.drop_index('ix_groups_ad_dn', table_name='groups')
    op.drop_index('ix_groups_code', table_name='groups')
    op.drop_table('groups')

    op.drop_index('ix_permissions_module_code', table_name='permissions')
    op.drop_index('ix_permissions_code', table_name='permissions')
    op.drop_table('permissions')

    op.drop_index('ix_roles_code_active', table_name='roles')
    op.drop_index('ix_roles_code', table_name='roles')
    op.drop_table('roles')