"""Service métier du module Photos.

Toutes les lectures sont scopées au propriétaire courant ; l'accès transverse
nécessite la permission explicite ``photos.manage_all`` (les photos sont
privées par défaut). Aucune requête N+1 : les listes sont préchargées en une
main query + jointures d'agrégation.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import and_, exists, func, or_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import (
    Photo,
    PhotoAlbum,
    PhotoAlbumItem,
    PhotoEdit,
    PhotoFace,
    PhotoJob,
    PhotoPerson,
    PhotoPlace,
    PhotoTag,
    PhotoTagLink,
    PhotoThumbnail,
)
from app.models.user import User
from app.schemas.photos import (
    PhotoAlbumListParams,
    PhotoDuplicateGroup,
    PhotoListParams,
)
from app.services.photo.ai_search import build_search_filters
from app.services.photo.face_grouping import is_auto_name
from app.services.photo.storage import PhotoStorage, PhotoStorageError, get_photo_storage

logger = logging.getLogger(__name__)

MIME_BY_FORMAT = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "ico": "image/x-icon",
    # HEIC/HEIF (iPhone) : supportés si pillow-heif installé.
    "heic": "image/heic",
    "heif": "image/heif",
}

ALLOWED_FORMATS = set(MIME_BY_FORMAT) | {"mpo"}


class PhotoServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PhotoNotFound(Exception):
    pass


def _slug(value: str) -> str:
    from app.services.photo.analysis import slugify

    return slugify(value)


# ------------------------------------------------------------------ curseur

def encode_cursor(taken_at: datetime, photo_id: int) -> str:
    raw = f"{taken_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}|{photo_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    padded = cursor + "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(padded.encode()).decode()
    stamp, _, photo_id = raw.partition("|")
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%f"), int(photo_id)


class PhotoService:
    def __init__(
        self,
        db: AsyncSession,
        current_user: User,
        audit=None,
        storage: PhotoStorage | None = None,
    ):
        self.db = db
        self.current_user = current_user
        self.audit = audit
        self.storage = storage or get_photo_storage()
        self._manage_all: bool | None = None

    # ----------------------------------------------------------- permissions
    async def can_manage_all(self) -> bool:
        if self._manage_all is None:
            from app.services.rbac import RBACService

            self._manage_all = await RBACService(self.db).user_has_permission(
                self.current_user, "photos.manage_all"
            )
        return self._manage_all

    def _owner_clause(self, owner_id: int | None = None):
        return Photo.owner_id == (owner_id if owner_id is not None else self.current_user.id)

    async def _get_owned(self, photo_id: int, *, include_deleted: bool = False) -> Photo:
        photo = await self.db.get(Photo, photo_id)
        if photo is None or photo.owner_id != self.current_user.id:
            if not await self.can_manage_all():
                raise PhotoNotFound()
            if photo is None:
                raise PhotoNotFound()
        if photo.is_deleted and not include_deleted:
            raise PhotoNotFound()
        return photo

    # ------------------------------------------------------------- import
    async def upload_files(
        self, files: list
    ) -> tuple[list[Photo], list[dict[str, str]]]:
        """Importe des fichiers : original sur disque + ligne + job d'ingest.

        La photo apparaît immédiatement (statut « pending ») : métadonnées et
        miniatures sont produites par le job d'arrière-plan.
        """
        from app.services.photo.jobs import enqueue_job

        settings = get_settings()
        created: list[Photo] = []
        errors: list[dict[str, str]] = []

        for upload in files:
            filename = Path(upload.filename or "photo").name[:500] or "photo"
            try:
                data = await upload.read(settings.PHOTO_MAX_UPLOAD_SIZE + 1)
            except Exception as exc:  # noqa: BLE001
                errors.append({"filename": filename, "error": f"Lecture impossible: {exc}"})
                continue

            if len(data) > settings.PHOTO_MAX_UPLOAD_SIZE:
                errors.append(
                    {
                        "filename": filename,
                        "error": f"Fichier trop volumineux (max {settings.PHOTO_MAX_UPLOAD_SIZE} octets)",
                    }
                )
                continue
            if not data:
                errors.append({"filename": filename, "error": "Fichier vide"})
                continue

            image_format = await sniff_image_format_maybe(data)
            if not image_format:
                errors.append({"filename": filename, "error": "Format d'image non reconnu"})
                continue
            if image_format not in ALLOWED_FORMATS:
                errors.append(
                    {"filename": filename, "error": f"Format non supporté: {image_format}"}
                )
                continue

            mime_type = MIME_BY_FORMAT.get(image_format, f"image/{image_format}")
            content_hash = self.storage.hash_bytes(data)
            backend = self.storage.backend()
            rel = self.storage.save_original(
                self.current_user.id, uuid4().hex, f".{image_format}", data
            )

            photo = Photo(
                owner_id=self.current_user.id,
                title=None,
                original_filename=filename,
                storage_path=rel,
                storage_backend=backend.name,
                mime_type=mime_type,
                byte_size=len(data),
                taken_at=datetime.now(),
                content_hash=content_hash,
                status="pending",
                analysis_status="pending",
            )
            # Photo + job dans une transaction unique : si l'enregistrement
            # échoue, on efface le fichier écrit au préalable (pas d'orphelin
            # sur disque, pas de photo « pending » sans job).
            try:
                self.db.add(photo)
                await self.db.flush()
                await enqueue_job(
                    self.db, type="ingest", photo_id=photo.id, commit=False
                )
                await self.db.commit()
                await self.db.refresh(photo)
            except Exception as exc:  # noqa: BLE001 - un fichier en échec n'annule pas les autres
                logger.exception("[PHOTO] import impossible: %s", filename)
                await self.db.rollback()
                # Échec d'import : le fichier que NOUS venons d'écrire est
                # retiré du backend utilisé (no-op garanti côté NAS).
                self.storage.delete_original(rel, backend.name)
                errors.append(
                    {"filename": filename, "error": f"Import impossible: {type(exc).__name__}"}
                )
                continue
            created.append(photo)

        return created, errors

    # --------------------------------------------------------------- lecture
    def _apply_filters(self, query, params: PhotoListParams, owner_id: int | None = None):
        filters = [self._owner_clause(owner_id)]
        if not params.include_deleted:
            filters.append(Photo.is_deleted.is_(False))
        if params.favorite is not None:
            filters.append(Photo.is_favorite.is_(params.favorite))
        if params.place_id is not None:
            filters.append(Photo.place_id == params.place_id)
        if params.date_from is not None:
            filters.append(Photo.taken_at >= datetime.combine(params.date_from, time.min))
        if params.date_to is not None:
            filters.append(
                Photo.taken_at
                < datetime.combine(params.date_to + timedelta(days=1), time.min)
            )
        if params.album_id is not None:
            filters.append(
                exists().where(
                    PhotoAlbumItem.photo_id == Photo.id,
                    PhotoAlbumItem.album_id == params.album_id,
                )
            )
        if params.person_id is not None:
            filters.append(
                exists().where(
                    PhotoFace.photo_id == Photo.id,
                    PhotoFace.person_id == params.person_id,
                )
            )
        if params.tag:
            tag_slug = _slug(params.tag)
            filters.append(
                exists().where(
                    PhotoTagLink.photo_id == Photo.id,
                    PhotoTagLink.tag_id == PhotoTag.id,
                    PhotoTag.owner_id == Photo.owner_id,
                    or_(PhotoTag.slug == tag_slug, PhotoTag.name.ilike(f"%{params.tag}%")),
                )
            )
        if params.search:
            pattern = f"%{params.search}%"
            filters.append(
                or_(
                    Photo.title.ilike(pattern),
                    Photo.original_filename.ilike(pattern),
                    Photo.camera_model.ilike(pattern),
                    Photo.camera_make.ilike(pattern),
                    exists().where(
                        PhotoTagLink.photo_id == Photo.id,
                        PhotoTagLink.tag_id == PhotoTag.id,
                        or_(PhotoTag.name.ilike(pattern), PhotoTag.slug.ilike(pattern)),
                    ),
                )
            )
        return query.where(*filters)

    def _apply_nl_filters(self, query, filters: dict[str, Any]):
        if filters.get("favorite"):
            query = query.where(Photo.is_favorite.is_(True))
        if filters.get("place_ids"):
            query = query.where(Photo.place_id.in_(filters["place_ids"]))
        if filters.get("place_name"):
            query = query.where(
                exists().where(
                    Photo.place_id == PhotoPlace.id,
                    PhotoPlace.label.ilike(f"%{filters['place_name']}%"),
                )
            )
        person_ids = list(filters.get("person_ids") or [])
        if person_ids:
            query = query.where(
                exists().where(
                    PhotoFace.photo_id == Photo.id,
                    PhotoFace.person_id.in_(person_ids),
                )
            )
        tag_ids = list(filters.get("tag_ids") or [])
        if tag_ids:
            query = query.where(
                exists().where(
                    PhotoTagLink.photo_id == Photo.id,
                    PhotoTagLink.tag_id.in_(tag_ids),
                )
            )
        date_from = filters.get("date_from")
        if date_from:
            query = query.where(Photo.taken_at >= datetime.fromisoformat(str(date_from)))
        date_to = filters.get("date_to")
        if date_to:
            query = query.where(
                Photo.taken_at
                < datetime.fromisoformat(str(date_to)) + timedelta(days=1)
            )
        free_text = (filters.get("free_text") or "").strip()
        if free_text:
            pattern = f"%{free_text}%"
            query = query.where(
                or_(
                    Photo.title.ilike(pattern),
                    Photo.original_filename.ilike(pattern),
                    Photo.camera_model.ilike(pattern),
                    # Lieux : label et pays participent au texte libre
                    # (« photos en Espagne » même sans cellule GPS résolue).
                    exists().where(
                        Photo.place_id == PhotoPlace.id,
                        or_(
                            PhotoPlace.label.ilike(pattern),
                            PhotoPlace.country.ilike(pattern),
                        ),
                    ),
                    exists().where(
                        PhotoTagLink.photo_id == Photo.id,
                        PhotoTagLink.tag_id == PhotoTag.id,
                        or_(PhotoTag.name.ilike(pattern), PhotoTag.slug.ilike(pattern)),
                    ),
                )
            )
        return query

    async def _resolve_people_names(self, names: list[str]) -> list[int]:
        resolved: list[int] = []
        for name in names:
            result = await self.db.execute(
                select(PhotoPerson.id).where(
                    PhotoPerson.owner_id == self.current_user.id,
                    PhotoPerson.name.ilike(name.strip()),
                )
            )
            resolved.extend(result.scalars().all())
        return resolved

    async def list_photos(
        self, params: PhotoListParams, extra_filters: dict[str, Any] | None = None
    ) -> tuple[list[Photo], int, Optional[str]]:
        base = select(Photo)
        base = self._apply_filters(base, params)
        if extra_filters:
            base = self._apply_nl_filters(base, extra_filters)
            if extra_filters.get("people_names"):
                person_ids = await self._resolve_people_names(extra_filters["people_names"])
                if person_ids:
                    base = base.where(
                        exists().where(
                            PhotoFace.photo_id == Photo.id,
                            PhotoFace.person_id.in_(person_ids),
                        )
                    )

        count_query = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        sort_map = {"taken_at": Photo.taken_at, "imported_at": Photo.imported_at}
        sort_key = params.sort_by if params.sort_by in sort_map else "taken_at"
        sort_field = sort_map[sort_key]
        descending = params.sort_order == "desc"

        query = base
        if params.cursor:
            try:
                cursor_at, cursor_id = decode_cursor(params.cursor)
            except Exception:  # noqa: BLE001 - curseur corrompu ignoré
                cursor_at, cursor_id = None, None
            if cursor_at is not None:
                # Le curseur porte la valeur du champ de tri : le filtre doit
                # comparer ce même champ (et non toujours taken_at), sinon la
                # pagination saute/duplique des lignes avec sort_by=imported_at.
                if descending:
                    query = query.where(
                        or_(
                            sort_field < cursor_at,
                            and_(sort_field == cursor_at, Photo.id < cursor_id),
                        )
                    )
                else:
                    query = query.where(
                        or_(
                            sort_field > cursor_at,
                            and_(sort_field == cursor_at, Photo.id > cursor_id),
                        )
                    )

        if descending:
            query = query.order_by(sort_field.desc(), Photo.id.desc())
        else:
            query = query.order_by(sort_field.asc(), Photo.id.asc())
        query = query.limit(params.page_size)

        items = list((await self.db.execute(query)).scalars().all())
        next_cursor = None
        if items and len(items) == params.page_size:
            last = items[-1]
            next_cursor = encode_cursor(getattr(last, sort_key), last.id)
        return items, total, next_cursor

    async def search_natural(self, query_text: str, params: PhotoListParams):
        filters = await build_search_filters(self.db, self.current_user.id, query_text)
        # La requête brute est déjà traduite en filtres : on n'applique pas
        # en plus l'ilike littéral (qui ne matcherait plus « photos de X »).
        params.search = None
        return await self.list_photos(params, extra_filters=filters)

    async def get_photo(self, photo_id: int) -> Photo:
        return await self._get_owned(photo_id)

    async def get_photo_detail(self, photo_id: int) -> dict[str, Any]:
        photo = await self._get_owned(photo_id)
        tag_rows = (
            await self.db.execute(
                select(PhotoTag, PhotoTagLink.source)
                .join(PhotoTagLink, PhotoTagLink.tag_id == PhotoTag.id)
                .where(PhotoTagLink.photo_id == photo.id)
            )
        ).all()
        tags = [
            {
                "id": tag.id,
                "name": tag.name,
                "slug": tag.slug,
                "category": tag.category,
                "source": source or "manual",
            }
            for tag, source in tag_rows
        ]
        album_ids = (
            await self.db.execute(
                select(PhotoAlbumItem.album_id).where(
                    PhotoAlbumItem.photo_id == photo.id
                )
            )
        ).scalars().all()
        edits = (
            await self.db.execute(
                select(PhotoEdit)
                .where(PhotoEdit.photo_id == photo.id)
                .order_by(PhotoEdit.created_at.asc())
            )
        ).scalars().all()
        face_count = (
            await self.db.execute(
                select(func.count(PhotoFace.id)).where(PhotoFace.photo_id == photo.id)
            )
        ).scalar() or 0
        return {
            "photo": photo,
            "tags": tags,
            "album_ids": list(album_ids),
            "edits": edits,
            "face_count": face_count,
        }

    # ------------------------------------------------------------- écriture
    async def update_photo(self, photo_id: int, data: dict[str, Any]) -> Photo:
        photo = await self._get_owned(photo_id, include_deleted=True)
        if "title" in data:
            photo.title = data["title"]
        if "is_favorite" in data and data["is_favorite"] is not None:
            photo.is_favorite = bool(data["is_favorite"])
        await self.db.commit()
        await self.db.refresh(photo)
        return photo

    async def delete_photo(self, photo_id: int) -> Photo:
        """Suppression logique : rien n'est effacé sur le disque.

        Les visages restent en base mais sont neutralisés partout (compteurs,
        recherche, regroupement) tant que la photo est à la corbeille.
        """
        photo = await self._get_owned(photo_id)
        face_ids = (
            await self.db.execute(
                select(PhotoFace.id).where(PhotoFace.photo_id == photo.id)
            )
        ).scalars().all()
        if face_ids:
            # Couvertures de personnes pointant vers un visage de la photo :
            # neutralisées (le crop ne serait plus servable).
            await self.db.execute(
                sa_update(PhotoPerson)
                .where(PhotoPerson.cover_face_id.in_(face_ids))
                .values(cover_face_id=None)
            )
        photo.is_deleted = True
        photo.deleted_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(photo)
        if self.audit and self.current_user:
            await self.audit.log(
                action="delete",
                module="photos",
                user=self.current_user,
                object_type="photo",
                object_id=str(photo.id),
                object_repr=photo.original_filename,
            )
        return photo

    async def restore_photo(self, photo_id: int) -> Photo:
        photo = await self._get_owned(photo_id, include_deleted=True)
        photo.is_deleted = False
        photo.deleted_at = None
        await self.db.commit()
        await self.db.refresh(photo)
        return photo

    async def request_analysis(self, photo_id: int) -> PhotoJob:
        from app.services.photo.jobs import enqueue_job_unique

        photo = await self._get_owned(photo_id, include_deleted=True)
        photo.analysis_status = "pending"
        # Photo + job dans la même transaction : pas d'état « pending » sans
        # job si l'enregistrement du job échoue. Un job déjà en file est
        # réutilisé (pas de doublon « analyze » pour la même photo).
        job = await enqueue_job_unique(
            self.db, type="analyze", photo_id=photo.id, commit=False
        )
        await self.db.commit()
        return job

    async def request_embedding(self, photo_id: int) -> PhotoJob:
        """Ré-indexation vectorielle (force = recalcule même si à jour)."""
        from app.services.photo.jobs import enqueue_job_unique, find_active_job

        photo = await self._get_owned(photo_id, include_deleted=True)
        existing = await find_active_job(
            self.db, type="embedding", photo_id=photo.id
        )
        if existing is not None:
            # Un job est déjà en file : on y greffe l'intention de forcer
            # plutôt que d'en créer un second.
            existing.payload_json = {**(existing.payload_json or {}), "force": True}
            job = existing
        else:
            job = await enqueue_job_unique(
                self.db,
                type="embedding",
                photo_id=photo.id,
                payload={"force": True},
                commit=False,
            )
        await self.db.commit()
        return job

    async def find_similar(
        self, photo_id: int, limit: int = 12
    ) -> tuple[list[Photo], list[float], bool, str | None]:
        """Photos similaires (cosinus sur embeddings), scopées au propriétaire.

        Retourne ``(photos, scores, photo indexée, provider)``.
        """
        from app.services.photo.embeddings import find_similar_embeddings

        photo = await self._get_owned(photo_id)
        matches, indexed, provider = await find_similar_embeddings(
            self.db, photo, limit
        )
        if not matches:
            return [], [], indexed, provider
        ids = [candidate_id for candidate_id, _ in matches]
        rows = (
            await self.db.execute(
                select(Photo).where(
                    Photo.id.in_(ids),
                    Photo.owner_id == photo.owner_id,
                    Photo.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        by_id = {row.id: row for row in rows}
        photos: list[Photo] = []
        scores: list[float] = []
        for candidate_id, score in matches:
            row = by_id.get(candidate_id)
            if row is not None:
                photos.append(row)
                scores.append(score)
        return photos, scores, indexed, provider

    # ----------------------------------------------------------------- fichiers
    async def resolve_file(
        self, photo_id: int, size: str = "small"
    ) -> tuple[Path, str, str]:
        photo = await self._get_owned(photo_id)
        if size == "original":
            try:
                path = self.storage.backend_for_photo(photo).original_path(
                    photo.storage_path
                )
            except PhotoStorageError as exc:
                # Backend de la photo retiré de la configuration (ex. NAS
                # démonté) : 404 propre, jamais un 500.
                raise PhotoServiceError(
                    "Original inaccessible (backend de stockage non configuré)", 404
                ) from exc
            if not path.is_file():
                raise PhotoServiceError("Fichier original introuvable", 404)
            return path, photo.original_filename, photo.mime_type

        thumb = (
            await self.db.execute(
                select(PhotoThumbnail).where(
                    PhotoThumbnail.photo_id == photo.id,
                    PhotoThumbnail.size == size,
                )
            )
        ).scalar_one_or_none()
        if thumb is None:
            raise PhotoServiceError(
                "Miniature indisponible (import en cours de traitement)", 404
            )
        path = self.storage.thumbnail_path(thumb.storage_path)
        if not path.is_file():
            raise PhotoServiceError("Miniature manquante sur le disque", 404)
        return path, f"{photo.id}-{size}.jpg", "image/jpeg"

    async def resolve_edit_file(self, photo_id: int, edit_id: int) -> tuple[Path, str, str]:
        photo = await self._get_owned(photo_id)
        edit = await self.db.get(PhotoEdit, edit_id)
        if edit is None or edit.photo_id != photo.id:
            raise PhotoNotFound()
        path = self.storage.edit_path(edit.storage_path)
        if not path.is_file():
            raise PhotoServiceError("Version introuvable sur le disque", 404)
        suffix = "png" if path.suffix == ".png" else "jpg"
        mime = "image/png" if suffix == "png" else "image/jpeg"
        return path, f"{photo.id}-edit-{edit.id}.{suffix}", mime

    # ----------------------------------------------------------------- albums
    async def list_albums(
        self, params: PhotoAlbumListParams
    ) -> tuple[list[tuple[PhotoAlbum, int]], int]:
        count_query = select(func.count(PhotoAlbum.id)).where(
            PhotoAlbum.owner_id == self.current_user.id,
            PhotoAlbum.is_deleted.is_(False),
        )
        if params.search:
            count_query = count_query.where(PhotoAlbum.name.ilike(f"%{params.search}%"))
        total = (await self.db.execute(count_query)).scalar() or 0

        query = select(PhotoAlbum).where(
            PhotoAlbum.owner_id == self.current_user.id,
            PhotoAlbum.is_deleted.is_(False),
        )
        if params.search:
            query = query.where(PhotoAlbum.name.ilike(f"%{params.search}%"))

        counts = (
            select(
                PhotoAlbumItem.album_id.label("album_id"),
                func.count(PhotoAlbumItem.photo_id).label("photo_count"),
            )
            .join(Photo, Photo.id == PhotoAlbumItem.photo_id)
            .where(Photo.is_deleted.is_(False))
            .group_by(PhotoAlbumItem.album_id)
            .subquery()
        )
        query = (
            query.outerjoin(counts, counts.c.album_id == PhotoAlbum.id)
            .add_columns(func.coalesce(counts.c.photo_count, 0))
            .order_by(PhotoAlbum.updated_at.desc())
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
        rows = (await self.db.execute(query)).all()
        return [(row[0], int(row[1] or 0)) for row in rows], total

    async def create_album(self, data: dict[str, Any]) -> PhotoAlbum:
        album = PhotoAlbum(
            owner_id=self.current_user.id,
            name=data["name"].strip(),
            description=data.get("description"),
        )
        self.db.add(album)
        try:
            await self.db.commit()
        except Exception:  # noqa: BLE001 - violation d'unicité (owner, name)
            await self.db.rollback()
            raise PhotoServiceError("Un album porte déjà ce nom", 409) from None
        await self.db.refresh(album)
        return album

    async def _get_owned_album(self, album_id: int) -> PhotoAlbum:
        album = await self.db.get(PhotoAlbum, album_id)
        if album is None or album.owner_id != self.current_user.id or album.is_deleted:
            raise PhotoNotFound()
        return album

    async def get_album(self, album_id: int) -> tuple[PhotoAlbum, int]:
        album = await self._get_owned_album(album_id)
        count = (
            await self.db.execute(
                select(func.count(PhotoAlbumItem.photo_id))
                .join(Photo, Photo.id == PhotoAlbumItem.photo_id)
                .where(
                    PhotoAlbumItem.album_id == album.id,
                    Photo.is_deleted.is_(False),
                )
            )
        ).scalar() or 0
        return album, int(count)

    async def update_album(self, album_id: int, data: dict[str, Any]) -> PhotoAlbum:
        album = await self._get_owned_album(album_id)
        if data.get("name") is not None:
            album.name = data["name"].strip()
        if "description" in data:
            album.description = data["description"]
        if "cover_photo_id" in data:
            cover_id = data["cover_photo_id"]
            if cover_id is not None:
                cover = await self.db.get(Photo, cover_id)
                if cover is None or cover.owner_id != self.current_user.id:
                    raise PhotoNotFound()
            album.cover_photo_id = cover_id
        try:
            await self.db.commit()
        except Exception:  # noqa: BLE001 - violation d'unicité (owner, name)
            await self.db.rollback()
            raise PhotoServiceError("Un album porte déjà ce nom", 409) from None
        await self.db.refresh(album)
        return album

    async def delete_album(self, album_id: int) -> PhotoAlbum:
        album = await self._get_owned_album(album_id)
        album.is_deleted = True
        await self.db.commit()
        await self.db.refresh(album)
        return album

    async def add_album_photos(self, album_id: int, photo_ids: list[int]) -> int:
        album = await self._get_owned_album(album_id)
        photos = (
            await self.db.execute(
                select(Photo).where(
                    Photo.id.in_(photo_ids),
                    Photo.owner_id == self.current_user.id,
                    Photo.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        existing = (
            await self.db.execute(
                select(PhotoAlbumItem.photo_id).where(
                    PhotoAlbumItem.album_id == album.id
                )
            )
        ).scalars()
        existing_ids = set(existing)
        max_position = (
            await self.db.execute(
                select(func.coalesce(func.max(PhotoAlbumItem.position), 0)).where(
                    PhotoAlbumItem.album_id == album.id
                )
            )
        ).scalar() or 0
        added = 0
        for photo in photos:
            if photo.id in existing_ids:
                continue
            max_position += 1
            self.db.add(
                PhotoAlbumItem(album_id=album.id, photo_id=photo.id, position=max_position)
            )
            added += 1
        await self.db.commit()
        return added

    async def remove_album_photo(self, album_id: int, photo_id: int) -> bool:
        _album = await self._get_owned_album(album_id)
        item = await self.db.get(PhotoAlbumItem, (album_id, photo_id))
        if item is None:
            return False
        await self.db.delete(item)
        await self.db.commit()
        return True

    # --------------------------------------------------------------- personnes
    async def _person_counts(
        self, person_ids: list[int]
    ) -> dict[int, tuple[int, int]]:
        """(face_count, photo_count) dynamiques, sur photos non supprimées.

        Aucun compteur dénormalisé : la suppression d'une photo neutralise
        immédiatement ses visages dans les compteurs.
        """
        if not person_ids:
            return {}
        rows = (
            await self.db.execute(
                select(
                    PhotoFace.person_id,
                    func.count(PhotoFace.id),
                    func.count(func.distinct(PhotoFace.photo_id)),
                )
                .join(Photo, Photo.id == PhotoFace.photo_id)
                .where(
                    PhotoFace.person_id.in_(person_ids),
                    Photo.is_deleted.is_(False),
                )
                .group_by(PhotoFace.person_id)
            )
        ).all()
        return {row[0]: (int(row[1]), int(row[2])) for row in rows}

    async def list_people(self) -> list[tuple[PhotoPerson, int, int]]:
        """Personnes du propriétaire courant → (personne, visages, photos)."""
        people = (
            await self.db.execute(
                select(PhotoPerson)
                .where(PhotoPerson.owner_id == self.current_user.id)
                .order_by(PhotoPerson.name)
            )
        ).scalars().all()
        counts = await self._person_counts([person.id for person in people])
        return [
            (person, *counts.get(person.id, (0, 0))) for person in people
        ]

    async def get_person(self, person_id: int) -> PhotoPerson:
        person = await self.db.get(PhotoPerson, person_id)
        if person is None or person.owner_id != self.current_user.id:
            raise PhotoNotFound()
        return person

    async def get_person_counts(self, person_id: int) -> tuple[int, int]:
        counts = await self._person_counts([person_id])
        return counts.get(person_id, (0, 0))

    async def create_person(self, name: str) -> PhotoPerson:
        person = PhotoPerson(owner_id=self.current_user.id, name=name.strip())
        self.db.add(person)
        try:
            await self.db.commit()
        except Exception:  # noqa: BLE001
            await self.db.rollback()
            raise PhotoServiceError("Une personne porte déjà ce nom", 409) from None
        await self.db.refresh(person)
        return person

    async def update_person(self, person_id: int, name: str) -> PhotoPerson:
        person = await self.get_person(person_id)
        person.name = name.strip()
        try:
            await self.db.commit()
        except Exception:  # noqa: BLE001 - violation d'unicité (owner, name)
            await self.db.rollback()
            raise PhotoServiceError("Une personne porte déjà ce nom", 409) from None
        await self.db.refresh(person)
        return person

    async def set_person_cover(
        self, person_id: int, face_id: int | None
    ) -> PhotoPerson:
        """Change la couverture (visage du groupe, ou ``None`` pour effacer)."""
        person = await self.get_person(person_id)
        if face_id is not None:
            face = await self.db.get(PhotoFace, face_id)
            if face is None or face.person_id != person.id:
                raise PhotoServiceError("Le visage n'appartient pas à cette personne", 400)
            photo = await self.db.get(Photo, face.photo_id)
            if photo is None or photo.is_deleted:
                raise PhotoServiceError("Photo introuvable", 404)
        person.cover_face_id = face_id
        await self.db.commit()
        await self.db.refresh(person)
        return person

    async def delete_person(self, person_id: int) -> None:
        """Supprime le groupe : les visages sont DÉSASSOCIÉS (pas les photos)."""
        person = await self.get_person(person_id)
        faces = (
            await self.db.execute(select(PhotoFace).where(PhotoFace.person_id == person.id))
        ).scalars().all()
        for face in faces:
            face.person_id = None
        await self.db.delete(person)
        await self.db.commit()

    async def merge_people(self, person_id: int, source_id: int) -> PhotoPerson:
        """Fusionne ``source_id`` dans ``person_id`` (la cible survit).

        Les visages de la source rejoignent la cible ; si la cible porte
        encore un nom auto (« Personne N ») et que la source est nommée,
        le nom de la source est adopté (s'il est libre).
        """
        if person_id == source_id:
            raise PhotoServiceError("Une personne ne peut pas être fusionnée avec elle-même", 400)
        target = await self.get_person(person_id)
        source = await self.get_person(source_id)

        source_faces = (
            await self.db.execute(select(PhotoFace).where(PhotoFace.person_id == source.id))
        ).scalars().all()
        for face in source_faces:
            face.person_id = target.id
        # Flush AVANT la suppression de la source : sans lui, SQLAlchemy
        # rechargerait les visages comme « enfants » de la source et les
        # désassocierait (person_id = NULL) pendant le DELETE.
        await self.db.flush()

        # Adoption du nom de la source si la cible porte encore un nom auto
        # (« Personne N ») : à écrire APRÈS le DELETE de la source, sinon la
        # contrainte (owner_id, name) est violée pendant le flush.
        source_name = source.name
        source_cover = source.cover_face_id
        adopt_name = (
            is_auto_name(target.name)
            and not is_auto_name(source_name)
            and target.owner_id == source.owner_id
        )
        if adopt_name:
            clash = (
                await self.db.execute(
                    select(PhotoPerson.id).where(
                        PhotoPerson.owner_id == target.owner_id,
                        PhotoPerson.name == source_name,
                        PhotoPerson.id.notin_([target.id, source.id]),
                    )
                )
            ).scalar_one_or_none()
            adopt_name = clash is None

        await self.db.delete(source)
        await self.db.flush()

        if adopt_name:
            target.name = source_name
        if target.cover_face_id is None and source_cover is not None:
            target.cover_face_id = source_cover

        await self.db.commit()
        await self.db.refresh(target)
        return target

    async def list_person_faces(self, person_id: int) -> list[PhotoFace]:
        """Visages du groupe (photos non supprimées), ordre stable."""
        person = await self.get_person(person_id)
        result = await self.db.execute(
            select(PhotoFace)
            .join(Photo, Photo.id == PhotoFace.photo_id)
            .where(
                PhotoFace.person_id == person.id,
                Photo.is_deleted.is_(False),
            )
            .order_by(PhotoFace.photo_id, PhotoFace.id)
        )
        return list(result.scalars().all())

    async def assign_face(self, face_id: int, person_id: int | None) -> PhotoFace:
        face = await self.db.get(PhotoFace, face_id)
        if face is None:
            raise PhotoNotFound()
        photo = await self.db.get(Photo, face.photo_id)
        if photo is None or photo.owner_id != self.current_user.id:
            if not await self.can_manage_all():
                raise PhotoNotFound()
        previous_person_id = face.person_id
        if person_id is not None:
            person = await self.db.get(PhotoPerson, person_id)
            if person is None or person.owner_id != self.current_user.id:
                raise PhotoNotFound()
        face.person_id = person_id
        if person_id is not None and not photo.is_deleted:
            # Première affectation → couverture par défaut.
            person = await self.db.get(PhotoPerson, person_id)
            if person is not None and person.cover_face_id is None:
                person.cover_face_id = face.id
        if (
            previous_person_id is not None
            and previous_person_id != person_id
        ):
            # L'ancien groupe peut être devenu vide : un groupe anonyme
            # vide est supprimé, un groupe nommé est conservé.
            old_person = await self.db.get(PhotoPerson, previous_person_id)
            if old_person is not None and is_auto_name(old_person.name):
                remaining = (
                    await self.db.execute(
                        select(PhotoFace.id)
                        .where(PhotoFace.person_id == old_person.id)
                        .limit(1)
                    )
                ).first()
                if remaining is None:
                    await self.db.delete(old_person)
        await self.db.commit()
        await self.db.refresh(face)
        return face

    async def unassign_face(self, face_id: int) -> PhotoFace:
        """Séparation explicite : le visage redevient non affecté."""
        return await self.assign_face(face_id, None)

    async def request_face_detection(self, photo_id: int) -> PhotoJob:
        """Déclenche (ou force) la détection des visages d'une photo."""
        from app.services.photo.jobs import enqueue_job_unique, find_active_job

        photo = await self._get_owned(photo_id, include_deleted=True)
        existing = await find_active_job(
            self.db, type="face_detect", photo_id=photo.id
        )
        if existing is not None:
            existing.payload_json = {**(existing.payload_json or {}), "force": True}
            job = existing
        else:
            job = await enqueue_job_unique(
                self.db,
                type="face_detect",
                photo_id=photo.id,
                payload={"force": True},
                commit=False,
            )
        await self.db.commit()
        return job

    async def resolve_face_crop(
        self, face_id: int, size: str = "small"
    ) -> bytes:
        """JPEG recadré sur le visage (miniature), original intact.

        Donnée privée : la photo est vérifiée au propriétaire (ou
        ``photos.manage_all``) — le crop ne transite jamais par un
        service externe.
        """
        face = await self.db.get(PhotoFace, face_id)
        if face is None:
            raise PhotoNotFound()
        photo = await self.db.get(Photo, face.photo_id)
        if photo is None or photo.owner_id != self.current_user.id:
            if not await self.can_manage_all():
                raise PhotoNotFound()
        if photo.is_deleted:
            raise PhotoNotFound()

        thumb = (
            await self.db.execute(
                select(PhotoThumbnail).where(
                    PhotoThumbnail.photo_id == photo.id,
                    PhotoThumbnail.size == size,
                )
            )
        ).scalar_one_or_none()
        if thumb is None:
            raise PhotoServiceError("Miniature indisponible", 404)
        path = self.storage.thumbnail_path(thumb.storage_path)
        if not path.is_file():
            raise PhotoServiceError("Miniature manquante sur le disque", 404)

        def _crop() -> bytes:
            from PIL import Image

            with Image.open(path) as source:
                image = source.convert("RGB")
                left = min(image.width - 1, max(0, int(face.x * image.width)))
                top = min(image.height - 1, max(0, int(face.y * image.height)))
                width = max(
                    1,
                    min(image.width - left, int(round(face.w * image.width))),
                )
                height = max(
                    1,
                    min(image.height - top, int(round(face.h * image.height))),
                )
                # Cadrage carré autour du centre du visage (marges comprises).
                side = max(width, height)
                center_x = left + width // 2
                center_y = top + height // 2
                crop_left = min(image.width - side, max(0, center_x - side // 2))
                crop_top = min(image.height - side, max(0, center_y - side // 2))
                box = (
                    crop_left,
                    crop_top,
                    min(image.width, crop_left + side),
                    min(image.height, crop_top + side),
                )
                square = image.crop(box)
                target = 256 if size in ("medium", "large", "preview") else 128
                square = square.resize((target, target))
                import io

                buffer = io.BytesIO()
                square.save(buffer, format="JPEG", quality=85)
                return buffer.getvalue()

        return await asyncio.to_thread(_crop)

    # ------------------------------------------------------------------- tags
    async def list_tags(self) -> list[tuple[PhotoTag, int]]:
        tags = (
            await self.db.execute(
                select(PhotoTag)
                .where(PhotoTag.owner_id == self.current_user.id)
                .order_by(PhotoTag.name)
            )
        ).scalars().all()
        if not tags:
            return []
        counts = (
            await self.db.execute(
                select(PhotoTagLink.tag_id, func.count(func.distinct(PhotoTagLink.photo_id)))
                .join(Photo, Photo.id == PhotoTagLink.photo_id)
                .where(
                    PhotoTagLink.tag_id.in_([t.id for t in tags]),
                    Photo.is_deleted.is_(False),
                )
                .group_by(PhotoTagLink.tag_id)
            )
        ).all()
        count_map = {row[0]: int(row[1] or 0) for row in counts}
        return [(tag, count_map.get(tag.id, 0)) for tag in tags]

    async def add_tag_to_photo(
        self, photo_id: int, name: str, category: str | None = "manual"
    ) -> PhotoTag:
        photo = await self._get_owned(photo_id)
        from app.services.photo.analysis import get_or_create_tag, link_tag

        tag = await get_or_create_tag(self.db, self.current_user.id, name, category)
        await link_tag(self.db, photo, tag, source="manual")
        await self.db.commit()
        return tag

    async def remove_tag_from_photo(self, photo_id: int, tag_id: int) -> bool:
        photo = await self._get_owned(photo_id, include_deleted=True)
        link = await self.db.get(PhotoTagLink, (photo.id, tag_id))
        if link is None:
            return False
        await self.db.delete(link)
        await self.db.commit()
        return True

    # ------------------------------------------------------------------ lieux
    async def list_places(self) -> list[tuple[PhotoPlace, int]]:
        rows = (
            await self.db.execute(
                select(PhotoPlace, func.count(Photo.id))
                .join(Photo, Photo.place_id == PhotoPlace.id)
                .where(
                    Photo.owner_id == self.current_user.id,
                    Photo.is_deleted.is_(False),
                )
                .group_by(PhotoPlace.id)
                .order_by(func.count(Photo.id).desc())
            )
        ).all()
        return [(row[0], int(row[1] or 0)) for row in rows]

    # --------------------------------------------------------------- doublons
    async def list_duplicates(self) -> list[PhotoDuplicateGroup]:
        rows = (
            await self.db.execute(
                select(Photo.content_hash, func.count(Photo.id))
                .where(
                    Photo.owner_id == self.current_user.id,
                    Photo.is_deleted.is_(False),
                )
                .group_by(Photo.content_hash)
                .having(func.count(Photo.id) > 1)
            )
        ).all()
        if not rows:
            return []
        hashes = [row[0] for row in rows]
        photo_rows = (
            await self.db.execute(
                select(Photo.content_hash, Photo.id).where(
                    Photo.owner_id == self.current_user.id,
                    Photo.content_hash.in_(hashes),
                    Photo.is_deleted.is_(False),
                )
            )
        ).all()
        grouped: dict[str, list[int]] = {}
        for content_hash, photo_id in photo_rows:
            grouped.setdefault(content_hash, []).append(photo_id)
        return [
            PhotoDuplicateGroup(
                content_hash=content_hash,
                count=len(photo_ids),
                photo_ids=sorted(photo_ids),
            )
            for content_hash, photo_ids in grouped.items()
        ]

    # ------------------------------------------------------------------- jobs
    async def list_jobs(self, limit: int = 50) -> list[PhotoJob]:
        return list(
            (
                await self.db.execute(
                    select(PhotoJob)
                    .join(Photo, Photo.id == PhotoJob.photo_id)
                    .where(
                        Photo.owner_id == self.current_user.id,
                        PhotoJob.status.in_(("pending", "running", "failed")),
                    )
                    .order_by(PhotoJob.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        )


async def sniff_image_format_maybe(data: bytes) -> str | None:
    from app.services.photo.metadata import sniff_image_format

    return await asyncio.to_thread(sniff_image_format, data)
