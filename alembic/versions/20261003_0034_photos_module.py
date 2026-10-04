"""Add photos module tables

Revision ID: 20261003_0034
Revises: 20260930_0033
Create Date: 2026-10-03

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20261003_0034'
down_revision = '20260930_0033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'photo_places',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lat_cell', sa.Float(), nullable=False),
        sa.Column('lon_cell', sa.Float(), nullable=False),
        sa.Column('label', sa.String(200), nullable=False, server_default=''),
        sa.Column('country', sa.String(100), nullable=True),
        sa.Column('source', sa.String(30), nullable=False, server_default='coords'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lat_cell', 'lon_cell', name='uq_photo_place_cell'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'photos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=False),
        # V3 : backend d'originaux de la photo ("local" | "nas").
        sa.Column('storage_backend', sa.String(20), nullable=False, server_default='local'),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('taken_at', sa.DateTime(), nullable=False),
        sa.Column('imported_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('gps_latitude', sa.Float(), nullable=True),
        sa.Column('gps_longitude', sa.Float(), nullable=True),
        sa.Column('place_id', sa.Integer(), nullable=True),
        sa.Column('camera_make', sa.String(100), nullable=True),
        sa.Column('camera_model', sa.String(100), nullable=True),
        sa.Column('exif_json', sa.JSON(), nullable=True),
        sa.Column('is_favorite', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('analysis_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['place_id'], ['photo_places.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photos_owner_id', 'photos', ['owner_id'])
    op.create_index('ix_photos_taken_at', 'photos', ['taken_at'])
    op.create_index('ix_photos_content_hash', 'photos', ['content_hash'])
    op.create_index('ix_photos_place_id', 'photos', ['place_id'])
    op.create_index('ix_photos_is_deleted', 'photos', ['is_deleted'])
    op.create_index('ix_photos_owner_taken', 'photos', ['owner_id', 'taken_at'])
    op.create_index('ix_photos_owner_deleted_taken', 'photos', ['owner_id', 'is_deleted', 'taken_at'])
    op.create_index('ix_photos_owner_hash', 'photos', ['owner_id', 'content_hash'])
    op.create_index('ix_photos_owner_favorite', 'photos', ['owner_id', 'is_favorite'])

    op.create_table(
        'photo_thumbnails',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('size', sa.String(20), nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('photo_id', 'size', name='uq_photo_thumbnail_size'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_thumbnails_photo_id', 'photo_thumbnails', ['photo_id'])

    op.create_table(
        'photo_albums',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cover_photo_id', sa.Integer(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['cover_photo_id'], ['photos.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'name', name='uq_photo_album_owner_name'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_albums_owner_id', 'photo_albums', ['owner_id'])

    op.create_table(
        'photo_album_items',
        sa.Column('album_id', sa.Integer(), nullable=False),
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['album_id'], ['photo_albums.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('album_id', 'photo_id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    # La PK (album_id, photo_id) ne peut pas servir les recherches par
    # photo_id : index dédié pour le détail d'une photo (ses albums).
    op.create_index('ix_photo_album_items_photo_id', 'photo_album_items', ['photo_id'])

    op.create_table(
        'photo_people',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('cover_face_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'name', name='uq_photo_person_owner_name'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_people_owner_id', 'photo_people', ['owner_id'])

    # Les compteurs (visages / photos) sont calculés dynamiquement :
    # aucune colonne dénormalisée à maintenir après suppression de photo.
    op.create_table(
        'photo_faces',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=True),
        sa.Column('x', sa.Float(), nullable=False),
        sa.Column('y', sa.Float(), nullable=False),
        sa.Column('w', sa.Float(), nullable=False),
        sa.Column('h', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('detector', sa.String(50), nullable=False),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('embedding_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['person_id'], ['photo_people.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_faces_photo_id', 'photo_faces', ['photo_id'])
    op.create_index('ix_photo_faces_person_id', 'photo_faces', ['person_id'])

    # Couverture de personne → visage (cycle géré : table créée après
    # photo_faces, contrainte ajoutée en second temps).
    op.create_foreign_key(
        'fk_photo_people_cover_face_id',
        'photo_people',
        'photo_faces',
        ['cover_face_id'],
        ['id'],
        ondelete='SET NULL',
    )

    op.create_table(
        'photo_tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(120), nullable=False),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'slug', name='uq_photo_tag_owner_slug'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_tags_owner_id', 'photo_tags', ['owner_id'])

    op.create_table(
        'photo_tag_links',
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['photo_tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('photo_id', 'tag_id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_tag_links_tag_id', 'photo_tag_links', ['tag_id'])

    op.create_table(
        'photo_analyses',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('provider', sa.String(50), nullable=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_analyses_photo_id', 'photo_analyses', ['photo_id'])

    # Vecteurs d'images : une ligne par photo, ré-écrite à chaque changement
    # de provider / modèle / version (voir app/services/photo/embeddings.py).
    # JSON dans la base applicative (MySQL 8.4 n'a pas de type vector) : pas
    # de dépendance supplémentaire, le calcul de similarité est fait en Python.
    op.create_table(
        'photo_embeddings',
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('dimensions', sa.Integer(), nullable=False),
        sa.Column('vector_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('photo_id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'photo_edits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('parent_edit_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('name', sa.String(150), nullable=True),
        sa.Column('params_json', sa.JSON(), nullable=True),
        sa.Column('storage_path', sa.String(500), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_edit_id'], ['photo_edits.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_edits_photo_id', 'photo_edits', ['photo_id'])

    op.create_table(
        'photo_jobs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('photo_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('available_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_jobs_photo_id', 'photo_jobs', ['photo_id'])
    op.create_index('ix_photo_jobs_status_available', 'photo_jobs', ['status', 'available_at'])

    # V3 : trace des scans/import de stockage (dernier état affiché dans
    # l'interface « Stockage »).
    op.create_table(
        'photo_scan_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('backend', sa.String(20), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('files_seen', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_paths', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('missing_marked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_photo_scan_runs_owner_id', 'photo_scan_runs', ['owner_id'])
    op.create_index(
        'ix_photo_scan_runs_backend_started', 'photo_scan_runs', ['backend', 'started_at']
    )


def downgrade() -> None:
    op.drop_table('photo_scan_runs')
    op.drop_table('photo_embeddings')
    op.drop_table('photo_jobs')
    op.drop_table('photo_edits')
    op.drop_table('photo_analyses')
    op.drop_table('photo_tag_links')
    op.drop_table('photo_tags')
    # Cycle photo_people <-> photo_faces : la FK de couverture est retirée
    # avant les tables (sinon MySQL refuse le DROP).
    op.drop_constraint('fk_photo_people_cover_face_id', 'photo_people', type_='foreignkey')
    op.drop_table('photo_faces')
    op.drop_table('photo_people')
    op.drop_index('ix_photo_album_items_photo_id', table_name='photo_album_items')
    op.drop_table('photo_album_items')
    op.drop_table('photo_albums')
    op.drop_table('photo_thumbnails')
    op.drop_table('photos')
    op.drop_table('photo_places')
