"""Supprime photo_people.face_count (colonne orpheline, absente du modèle)

``photo_people.face_count`` (INT NOT NULL, sans valeur par défaut) n'est pas
déclarée dans le modèle ``PhotoPerson`` : chaque INSERT de groupe échouait sur
``Field 'face_count' doesn't have a default value``, annulait la transaction du
job ``face_embedding`` (les ``attempts`` n'étaient jamais persistés) et faisait
 rejouer indéfiniment le même job. La table est vide et la colonne n'est jamais
lue (les compteurs sont calculés dynamiquement).

Revision ID: 20261007_0038
Revises: 20261006_0037
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261007_0038'
down_revision = '20261006_0037'
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, 'photo_people', 'face_count'):
        op.drop_column('photo_people', 'face_count')


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, 'photo_people', 'face_count'):
        op.add_column(
            'photo_people',
            sa.Column('face_count', sa.Integer(), nullable=False, server_default='0'),
        )
