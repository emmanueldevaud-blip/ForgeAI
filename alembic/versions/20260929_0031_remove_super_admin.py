"""Remove super_admin role (kept: admin only)

Revision ID: 20260929_0031
Revises: 20260928_0030
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260929_0031"
down_revision = "20260928_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Le rôle super_admin n'existe plus : seuls les rôles admin et user subsistent.
    op.execute("""
        DELETE FROM role_permissions
        WHERE role_id IN (SELECT id FROM roles WHERE code = 'super_admin')
    """)
    op.execute("""
        DELETE FROM user_roles
        WHERE role_id IN (SELECT id FROM roles WHERE code = 'super_admin')
    """)
    op.execute("""
        DELETE FROM group_roles
        WHERE role_id IN (SELECT id FROM roles WHERE code = 'super_admin')
    """)
    op.execute("DELETE FROM roles WHERE code = 'super_admin'")


def downgrade() -> None:
    # Recrée le rôle et lui réattribue toutes les permissions existantes.
    op.execute("""
        INSERT INTO roles (code, name, description, is_system, is_active, created_at, updated_at)
        VALUES ('super_admin', 'Super Administrateur',
                'Rôle super administrateur avec tous les droits', 1, 1,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id, created_at)
        SELECT r.id, p.id, CURRENT_TIMESTAMP
        FROM roles r, permissions p
        WHERE r.code = 'super_admin'
    """)
