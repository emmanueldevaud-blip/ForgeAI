"""Add development agent tables

Revision ID: 20260930_0033
Revises: 20260930_0032
Create Date: 2026-09-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '20260930_0033'
down_revision = '20260930_0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'development_tasks',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('request', sa.Text(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, default='pending'),
        sa.Column('branch', sa.String(200), nullable=True),
        sa.Column('repository', sa.String(500), nullable=False, default='.'),
        sa.Column('opencode_session_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('test_results', sa.JSON(), nullable=False, default=dict),
        sa.Column('modified_files', sa.JSON(), nullable=False, default=list),
        sa.Column('diff_summary', sa.JSON(), nullable=False, default=dict),
        sa.Column('commit_hash', sa.String(40), nullable=True),
        sa.Column('push_status', sa.String(30), nullable=True),
        sa.Column('deployment_status', sa.String(30), nullable=True),
        sa.Column('current_step', sa.String(50), nullable=True),
        sa.Column('context', sa.JSON(), nullable=False, default=dict),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_development_tasks_user_status', 'development_tasks', ['user_id', 'status'])
    op.create_index('ix_development_tasks_created', 'development_tasks', ['created_at'])

    op.create_table(
        'development_agent_executions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.String(36), nullable=False),
        sa.Column('trigger', sa.String(50), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, default='pending'),
        sa.Column('provider', sa.String(50), nullable=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('step_count', sa.Integer(), nullable=False, default=0),
        sa.Column('steps_json', sa.JSON(), nullable=False, default=list),
        sa.Column('result_json', sa.JSON(), nullable=False, default=dict),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['development_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_development_agent_executions_task', 'development_agent_executions', ['task_id'])
    op.create_index('ix_development_agent_executions_started', 'development_agent_executions', ['started_at'])

    # Add relationship column to users table for development_tasks
    # The relationship is defined in the model via back_populates, no schema change needed


def downgrade() -> None:
    op.drop_index('ix_development_agent_executions_started', table_name='development_agent_executions')
    op.drop_index('ix_development_agent_executions_task', table_name='development_agent_executions')
    op.drop_table('development_agent_executions')
    op.drop_index('ix_development_tasks_created', table_name='development_tasks')
    op.drop_index('ix_development_tasks_user_status', table_name='development_tasks')
    op.drop_table('development_tasks')