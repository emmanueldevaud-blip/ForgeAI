"""Align photo_* tables with models (missing columns)

Les tables photo_analyses / photo_faces / photo_people ont été créées avant
l'ajout de ces colonnes dans les modèles (create_all puis migration 0034 déjà
consignée) : les jobs d'analyse échouent sur
``Unknown column 'photo_analyses.version'``. Migration additive uniquement.

Revision ID: 20261006_0037
Revises: 20261005_0036
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261006_0037'
down_revision = '20261005_0036'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, 'photo_analyses', 'version'):
        op.add_column(
            'photo_analyses',
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        )

    if not _has_column(bind, 'photo_faces', 'model'):
        op.add_column(
            'photo_faces',
            sa.Column('model', sa.String(100), nullable=True),
        )
    if not _has_column(bind, 'photo_faces', 'version'):
        op.add_column(
            'photo_faces',
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        )
    if not _has_column(bind, 'photo_faces', 'updated_at'):
        op.add_column(
            'photo_faces',
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
        )

    if not _has_column(bind, 'photo_people', 'cover_face_id'):
        op.add_column(
            'photo_people',
            sa.Column('cover_face_id', sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            'fk_photo_people_cover_face_id',
            'photo_people',
            'photo_faces',
            ['cover_face_id'],
            ['id'],
            ondelete='SET NULL',
        )
    if not _has_column(bind, 'photo_people', 'updated_at'):
        op.add_column(
            'photo_people',
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_column(bind, 'photo_people', 'updated_at'):
        op.drop_column('photo_people', 'updated_at')
    if _has_column(bind, 'photo_people', 'cover_face_id'):
        op.drop_constraint(
            'fk_photo_people_cover_face_id', 'photo_people', type_='foreignkey'
        )
        op.drop_column('photo_people', 'cover_face_id')

    if _has_column(bind, 'photo_faces', 'updated_at'):
        op.drop_column('photo_faces', 'updated_at')
    if _has_column(bind, 'photo_faces', 'version'):
        op.drop_column('photo_faces', 'version')
    if _has_column(bind, 'photo_faces', 'model'):
        op.drop_column('photo_faces', 'model')

    if _has_column(bind, 'photo_analyses', 'version'):
        op.drop_column('photo_analyses', 'version')
