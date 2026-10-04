"""API REST du module Photos."""

import logging
import urllib.parse
from typing import List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.core.config import get_settings
from app.models.user import User
from app.schemas.photos import (
    MessageResponse,
    PhotoAlbumCreate,
    PhotoAlbumListParams,
    PhotoAlbumListResponse,
    PhotoAlbumPhotosRequest,
    PhotoAlbumResponse,
    PhotoAlbumUpdate,
    PhotoAnalysisResponse,
    PhotoResponse,
    PhotoDetailResponse,
    PhotoDuplicateListResponse,
    PhotoEditCreate,
    PhotoEditResponse,
    PhotoFaceListResponse,
    PhotoFaceResponse,
    PhotoFaceUpdate,
    PhotoJobResponse,
    PhotoListParams,
    PhotoListResponse,
    PhotoPersonCreate,
    PhotoPersonListResponse,
    PhotoPersonMerge,
    PhotoPersonResponse,
    PhotoPersonUpdate,
    PhotoPlaceListResponse,
    PhotoScanQueuedResponse,
    PhotoScanRunResponse,
    PhotoSearchParams,
    PhotoSimilarItem,
    PhotoSimilarResponse,
    PhotoStorageStatusResponse,
    PhotoTagCreate,
    PhotoTagListResponse,
    PhotoTagResponse,
    PhotoThumbnailRebuildResponse,
    PhotoUpdate,
    PhotoUploadResponse,
)
from app.services.audit import get_audit_service
from app.services.photo.edits import (
    PhotoEditError,
    PhotoEditUnavailable,
    create_edit,
    revert_to_original,
)
from app.services.photo.jobs import (
    enqueue_job_unique,
    find_active_job,
    run_pending_jobs_now,
)
from app.services.photo.scan import last_scan_run
from app.services.photo.service import (
    PhotoNotFound,
    PhotoService,
    PhotoServiceError,
)
from app.services.photo.storage import PhotoStorageError, get_photo_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/photos", tags=["photos"])


# ================================ Dépendances ================================

async def _service(
    current_user: User = Depends(require_permission("photos.view")),
    db: AsyncSession = Depends(get_db),
) -> PhotoService:
    audit = await get_audit_service(db)
    return PhotoService(db, current_user, audit=audit)


async def _write_service(
    current_user: User = Depends(require_permission("photos.update")),
    db: AsyncSession = Depends(get_db),
) -> PhotoService:
    audit = await get_audit_service(db)
    return PhotoService(db, current_user, audit=audit)


async def _upload_service(
    current_user: User = Depends(require_permission("photos.upload")),
    db: AsyncSession = Depends(get_db),
) -> PhotoService:
    audit = await get_audit_service(db)
    return PhotoService(db, current_user, audit=audit)


async def _delete_service(
    current_user: User = Depends(require_permission("photos.delete")),
    db: AsyncSession = Depends(get_db),
) -> PhotoService:
    audit = await get_audit_service(db)
    return PhotoService(db, current_user, audit=audit)


async def _album_service(
    current_user: User = Depends(require_permission("photos.albums.manage")),
    db: AsyncSession = Depends(get_db),
) -> PhotoService:
    audit = await get_audit_service(db)
    return PhotoService(db, current_user, audit=audit)


async def _people_service(
    current_user: User = Depends(require_permission("photos.people.manage")),
    db: AsyncSession = Depends(get_db),
) -> PhotoService:
    audit = await get_audit_service(db)
    return PhotoService(db, current_user, audit=audit)


async def _edit_service(
    current_user: User = Depends(require_permission("photos.edit")),
    db: AsyncSession = Depends(get_db),
) -> PhotoService:
    audit = await get_audit_service(db)
    return PhotoService(db, current_user, audit=audit)


def _raise_not_found() -> None:
    raise HTTPException(status_code=404, detail="Photo non trouvée")


def _content_disposition(filename: str, *, download: bool) -> str:
    """En-tête sûr : latin-1 obligatoire pour les en-têtes HTTP.

    Sans filtre, un nom non latin-1 (CJK, arabe...) provoquerait une
    UnicodeEncodeError (500) ; sans échappement, un guillemet dans le nom
    casserait les guillemets du paramètre. RFC 6266/5987 : repli ASCII +
    ``filename*`` UTF-8.
    """
    kind = "attachment" if download else "inline"
    fallback = filename.encode("ascii", "ignore").decode("ascii")
    fallback = "".join(c for c in fallback if " " <= c <= "\x7f")
    fallback = fallback.replace('"', "").replace("\\", "").strip()
    if not any(ch.isalnum() for ch in fallback):
        # Nom entièrement non latin-1 : repli sur « photo » + extension.
        suffix = ""
        if "." in fallback:
            suffix = "." + fallback.rsplit(".", 1)[1][:10]
        fallback = f"photo{suffix}"
    encoded = urllib.parse.quote(filename, safe="")
    return f"{kind}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


# ================================ Photos ================================

@router.get("", response_model=PhotoListResponse)
async def list_photos(
    params: PhotoListParams = Depends(),
    service: PhotoService = Depends(_service),
):
    items, total, next_cursor = await service.list_photos(params)
    total_pages = max(1, -(-total // params.page_size)) if params.page_size else 1
    return PhotoListResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
        next_cursor=next_cursor,
    )


@router.get("/search", response_model=PhotoListResponse)
async def search_photos(
    params: PhotoSearchParams = Depends(),
    service: PhotoService = Depends(_service),
):
    list_params = PhotoListParams(
        page=params.page,
        page_size=params.page_size,
        favorite=params.favorite,
        album_id=params.album_id,
        person_id=params.person_id,
        place_id=params.place_id,
        date_from=params.date_from,
        date_to=params.date_to,
        cursor=params.cursor,
    )
    items, total, next_cursor = await service.search_natural(params.q, list_params)
    total_pages = max(1, -(-total // params.page_size)) if params.page_size else 1
    return PhotoListResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
        next_cursor=next_cursor,
    )


@router.get("/duplicates", response_model=PhotoDuplicateListResponse)
async def list_duplicates(service: PhotoService = Depends(_service)):
    groups = await service.list_duplicates()
    return PhotoDuplicateListResponse(groups=groups, total=len(groups))


@router.post(
    "/upload",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_photos(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    service: PhotoService = Depends(_upload_service),
):
    settings = get_settings()
    if not settings.PHOTO_ENABLED:
        raise HTTPException(status_code=404, detail="Module Photos désactivé")
    try:
        created, errors = await service.upload_files(files)
    except PhotoServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if not created and errors:
        raise HTTPException(status_code=400, detail=errors)
    if created and settings.PHOTO_BACKGROUND_JOBS:
        background_tasks.add_task(run_pending_jobs_now)
    return PhotoUploadResponse(items=created, errors=errors)


# ---------------------------------------------------------------- stockage (V3)

def _require_photos_enabled() -> None:
    if not get_settings().PHOTO_ENABLED:
        raise HTTPException(status_code=404, detail="Module Photos désactivé")


async def _storage_status(db: AsyncSession) -> PhotoStorageStatusResponse:
    """État du stockage courant (vérification réelle, pas de cache) + dernier
    scan persisté."""
    settings = get_settings()
    storage = get_photo_storage()
    backend_name = (settings.PHOTO_STORAGE_BACKEND or "local").strip()
    try:
        status = storage.check(backend_name)
    except PhotoStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    last = await last_scan_run(db, backend_name)
    return PhotoStorageStatusResponse(
        backend=backend_name,
        path=status.path,
        state=status.state,
        detail=status.detail,
        backends=storage.available_backends(),
        scan_enabled=settings.PHOTO_NAS_SCAN_ENABLED,
        scan_interval_seconds=settings.PHOTO_NAS_SCAN_INTERVAL_SECONDS,
        last_scan=PhotoScanRunResponse.model_validate(last) if last else None,
    )


@router.get("/storage/status", response_model=PhotoStorageStatusResponse)
async def photo_storage_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("photos.view")),
):
    """Statut du stockage d'originaux (backend, chemin, disponibilité,
    dernier scan). Usage interne à l'UI « Stockage »."""
    _require_photos_enabled()
    return await _storage_status(db)


@router.post("/import/scan", response_model=PhotoScanQueuedResponse, status_code=202)
async def photo_import_scan(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("photos.upload")),
):
    """Démarre un scan/import idempotent du répertoire de stockage courant.

    Jamais bloquant : le travail est enfilé en job ``scan_import`` ; aucun
    fichier n'est modifié ou supprimé. Un stockage ``unavailable`` refuse le
    scan avant tout traitement (409)."""
    _require_photos_enabled()
    settings = get_settings()
    storage = get_photo_storage()
    backend_name = (settings.PHOTO_STORAGE_BACKEND or "local").strip()
    try:
        status = storage.check(backend_name)
    except PhotoStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if status.state != "available":
        raise HTTPException(
            status_code=409,
            detail=f"Stockage {backend_name} indisponible ({status.state}) : {status.detail}",
        )

    existing = await find_active_job(db, type="scan_import", photo_id=None)
    if existing is not None:
        return PhotoScanQueuedResponse(
            queued=False,
            job_id=existing.id,
            message="Un scan est déjà en file",
        )

    job = await enqueue_job_unique(
        db,
        type="scan_import",
        photo_id=None,
        payload={"owner_id": current_user.id, "backend": backend_name},
    )
    if settings.PHOTO_BACKGROUND_JOBS:
        background_tasks.add_task(run_pending_jobs_now)
    return PhotoScanQueuedResponse(
        queued=True,
        job_id=job.id,
        message=f"Scan {backend_name} mis en file",
    )


@router.post(
    "/thumbnails/rebuild",
    response_model=PhotoThumbnailRebuildResponse,
    status_code=202,
)
async def photo_thumbnails_rebuild(
    background_tasks: BackgroundTasks,
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("photos.analyze")),
):
    """Remet en file la génération des miniatures **manquantes**.

    Cible uniquement les photos non supprimées sans aucune ligne de
    miniature (imports antérieurs à V3.1 : HEIC/vidéo sans codec).
    Asynchrone (jobs ``ingest`` dédoublonnés), progressive (``limit``),
    les miniatures déjà présentes ne sont pas touchées. Jamais d'accès à
    un original (NAS inclus)."""
    _require_photos_enabled()
    from sqlalchemy import exists, select

    from app.models.photo import Photo, PhotoThumbnail

    stmt = (
        select(Photo.id)
        .where(Photo.is_deleted.is_(False))
        .where(~exists().where(PhotoThumbnail.photo_id == Photo.id))
        .order_by(Photo.id)
        .limit(limit)
    )
    photo_ids = (await db.execute(stmt)).scalars().all()

    settings = get_settings()
    queued = 0
    for photo_id in photo_ids:
        await enqueue_job_unique(
            db, type="ingest", photo_id=photo_id, commit=False
        )
        queued += 1
    await db.commit()
    if queued and settings.PHOTO_BACKGROUND_JOBS:
        background_tasks.add_task(run_pending_jobs_now)
    return PhotoThumbnailRebuildResponse(
        queued=queued,
        message=(
            f"{queued} photo(s) sans miniature remise(s) en traitement"
            if queued
            else "Aucune photo sans miniature"
        ),
    )


@router.get("/albums", response_model=PhotoAlbumListResponse)
async def list_albums(
    params: PhotoAlbumListParams = Depends(),
    service: PhotoService = Depends(_service),
):
    rows, total = await service.list_albums(params)
    return PhotoAlbumListResponse(
        items=[
            PhotoAlbumResponse(
                id=album.id,
                owner_id=album.owner_id,
                name=album.name,
                description=album.description,
                cover_photo_id=album.cover_photo_id,
                photo_count=count,
                created_at=album.created_at,
                updated_at=album.updated_at,
            )
            for album, count in rows
        ],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=max(1, -(-total // params.page_size)),
    )


@router.post(
    "/albums", response_model=PhotoAlbumResponse, status_code=status.HTTP_201_CREATED
)
async def create_album(
    data: PhotoAlbumCreate,
    service: PhotoService = Depends(_album_service),
):
    album = await service.create_album(data.model_dump())
    return PhotoAlbumResponse(
        id=album.id,
        owner_id=album.owner_id,
        name=album.name,
        description=album.description,
        cover_photo_id=album.cover_photo_id,
        photo_count=0,
        created_at=album.created_at,
        updated_at=album.updated_at,
    )


@router.get("/albums/{album_id}", response_model=PhotoAlbumResponse)
async def get_album(album_id: int, service: PhotoService = Depends(_service)):
    try:
        album, count = await service.get_album(album_id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable") from None
    return PhotoAlbumResponse(
        id=album.id,
        owner_id=album.owner_id,
        name=album.name,
        description=album.description,
        cover_photo_id=album.cover_photo_id,
        photo_count=count,
        created_at=album.created_at,
        updated_at=album.updated_at,
    )


@router.patch("/albums/{album_id}", response_model=PhotoAlbumResponse)
async def update_album(
    album_id: int,
    data: PhotoAlbumUpdate,
    service: PhotoService = Depends(_album_service),
):
    try:
        album = await service.update_album(album_id, data.model_dump(exclude_unset=True))
        _, count = await service.get_album(album_id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable") from None
    return PhotoAlbumResponse(
        id=album.id,
        owner_id=album.owner_id,
        name=album.name,
        description=album.description,
        cover_photo_id=album.cover_photo_id,
        photo_count=count,
        created_at=album.created_at,
        updated_at=album.updated_at,
    )


@router.delete("/albums/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_album(
    album_id: int,
    service: PhotoService = Depends(_album_service),
):
    try:
        await service.delete_album(album_id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable") from None


@router.post("/albums/{album_id}/photos", response_model=MessageResponse)
async def add_album_photos(
    album_id: int,
    data: PhotoAlbumPhotosRequest,
    service: PhotoService = Depends(_album_service),
):
    try:
        added = await service.add_album_photos(album_id, data.photo_ids)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable") from None
    return MessageResponse(message=f"{added} photo(s) ajoutée(s)")


@router.delete(
    "/albums/{album_id}/photos/{photo_id}",
    response_model=MessageResponse,
)
async def remove_album_photo(
    album_id: int,
    photo_id: int,
    service: PhotoService = Depends(_album_service),
):
    try:
        removed = await service.remove_album_photo(album_id, photo_id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Album introuvable") from None
    if not removed:
        raise HTTPException(status_code=404, detail="Photo absente de l'album")
    return MessageResponse(message="Photo retirée de l'album")


# ================================ Personnes / visages ================================

def _person_response(
    person, face_count: int = 0, photo_count: int = 0
) -> PhotoPersonResponse:
    return PhotoPersonResponse(
        id=person.id,
        owner_id=person.owner_id,
        name=person.name,
        cover_face_id=person.cover_face_id,
        face_count=face_count,
        photo_count=photo_count,
        created_at=person.created_at,
    )


@router.get("/people", response_model=PhotoPersonListResponse)
async def list_people(service: PhotoService = Depends(_service)):
    rows = await service.list_people()
    return PhotoPersonListResponse(
        items=[
            _person_response(person, face_count, photo_count)
            for person, face_count, photo_count in rows
        ],
        total=len(rows),
    )


@router.post(
    "/people", response_model=PhotoPersonResponse, status_code=status.HTTP_201_CREATED
)
async def create_person(
    data: PhotoPersonCreate,
    service: PhotoService = Depends(_people_service),
):
    person = await service.create_person(data.name)
    return _person_response(person)


@router.get("/people/{person_id}", response_model=PhotoPersonResponse)
async def get_person(person_id: int, service: PhotoService = Depends(_service)):
    try:
        person = await service.get_person(person_id)
        face_count, photo_count = await service.get_person_counts(person.id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Personne introuvable") from None
    return _person_response(person, face_count, photo_count)


@router.get("/people/{person_id}/faces", response_model=PhotoFaceListResponse)
async def list_person_faces(person_id: int, service: PhotoService = Depends(_service)):
    """Visages du groupe (cadrages) — pour la fiche personne."""
    try:
        faces = await service.list_person_faces(person_id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Personne introuvable") from None
    return PhotoFaceListResponse(items=faces, total=len(faces))


@router.post(
    "/people/{person_id}/merge",
    response_model=PhotoPersonResponse,
)
async def merge_people(
    person_id: int,
    data: PhotoPersonMerge,
    service: PhotoService = Depends(_people_service),
):
    """Fusion de personnes.

    La route porte la **cible** (celle qui survit) ; le corps porte la
    **source** (absorbée : ses visages rejoignent la cible).
    """
    try:
        person = await service.merge_people(person_id, data.person_id)
        face_count, photo_count = await service.get_person_counts(person.id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Personne introuvable") from None
    except PhotoServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return _person_response(person, face_count, photo_count)


@router.patch("/people/{person_id}", response_model=PhotoPersonResponse)
async def update_person(
    person_id: int,
    data: PhotoPersonUpdate,
    service: PhotoService = Depends(_people_service),
):
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Nom ou couverture requis")
    try:
        person = await service.get_person(person_id)
        if "name" in payload:
            if not payload["name"]:
                raise HTTPException(status_code=400, detail="Nom requis")
            person = await service.update_person(person_id, payload["name"])
        if "cover_face_id" in payload:
            person = await service.set_person_cover(
                person_id, payload["cover_face_id"]
            )
        face_count, photo_count = await service.get_person_counts(person.id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Personne introuvable") from None
    except PhotoServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return _person_response(person, face_count, photo_count)


@router.delete("/people/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    person_id: int,
    service: PhotoService = Depends(_people_service),
):
    try:
        await service.delete_person(person_id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Personne introuvable") from None


@router.patch("/faces/{face_id}", response_model=PhotoFaceResponse)
async def assign_face(
    face_id: int,
    data: PhotoFaceUpdate,
    service: PhotoService = Depends(_people_service),
):
    try:
        face = await service.assign_face(face_id, data.person_id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Visage ou personne introuvable") from None
    return face


@router.post("/faces/{face_id}/unassign", response_model=PhotoFaceResponse)
async def unassign_face(
    face_id: int,
    service: PhotoService = Depends(_people_service),
):
    """Sépare un visage de son groupe (le visage n'est pas supprimé)."""
    try:
        face = await service.unassign_face(face_id)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Visage introuvable") from None
    return face


@router.get("/faces/{face_id}/crop")
async def get_face_crop(
    face_id: int,
    size: str = Query("small", max_length=20),
    service: PhotoService = Depends(_service),
):
    """Recadrage JPEG d'un visage (miniature, privé, jamais d'original modifié)."""
    try:
        content = await service.resolve_face_crop(face_id, size)
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Visage introuvable") from None
    except PhotoServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


# ================================ Tags / lieux / jobs ================================

@router.get("/tags", response_model=PhotoTagListResponse)
async def list_tags(service: PhotoService = Depends(_service)):
    rows = await service.list_tags()
    return PhotoTagListResponse(
        items=[
            PhotoTagResponse(
                id=tag.id,
                name=tag.name,
                slug=tag.slug,
                category=tag.category,
                photo_count=count,
            )
            for tag, count in rows
        ],
        total=len(rows),
    )


@router.get("/places", response_model=PhotoPlaceListResponse)
async def list_places(service: PhotoService = Depends(_service)):
    rows = await service.list_places()
    from app.schemas.photos import PhotoPlaceResponse

    return PhotoPlaceListResponse(
        items=[
            PhotoPlaceResponse(
                id=place.id,
                label=place.label,
                country=place.country,
                lat_cell=place.lat_cell,
                lon_cell=place.lon_cell,
                photo_count=count,
            )
            for place, count in rows
        ],
        total=len(rows),
    )


@router.get("/jobs", response_model=List[PhotoJobResponse])
async def list_jobs(service: PhotoService = Depends(_service)):
    return await service.list_jobs()


# ================================ Sous-ressources photo ================================

@router.get("/{photo_id}", response_model=PhotoDetailResponse)
async def get_photo(photo_id: int, service: PhotoService = Depends(_service)):
    try:
        detail = await service.get_photo_detail(photo_id)
    except PhotoNotFound:
        _raise_not_found()
    photo = detail["photo"]
    return PhotoDetailResponse(
        id=photo.id,
        owner_id=photo.owner_id,
        title=photo.title,
        original_filename=photo.original_filename,
        mime_type=photo.mime_type,
        byte_size=photo.byte_size,
        width=photo.width,
        height=photo.height,
        taken_at=photo.taken_at,
        imported_at=photo.imported_at,
        is_favorite=photo.is_favorite,
        status=photo.status,
        analysis_status=photo.analysis_status,
        gps_latitude=photo.gps_latitude,
        gps_longitude=photo.gps_longitude,
        camera_make=photo.camera_make,
        camera_model=photo.camera_model,
        is_deleted=photo.is_deleted,
        exif_json=photo.exif_json,
        place=photo.place,
        tags=detail["tags"],
        album_ids=detail["album_ids"],
        edits=detail["edits"],
        face_count=detail["face_count"],
        analysis_status_detail=photo.analysis_status,
    )


@router.patch("/{photo_id}", response_model=PhotoResponse)
async def update_photo(
    photo_id: int,
    data: PhotoUpdate,
    service: PhotoService = Depends(_write_service),
):
    try:
        return await service.update_photo(photo_id, data.model_dump(exclude_unset=True))
    except PhotoNotFound:
        _raise_not_found()


@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    photo_id: int,
    service: PhotoService = Depends(_delete_service),
):
    try:
        await service.delete_photo(photo_id)
    except PhotoNotFound:
        _raise_not_found()


@router.post("/{photo_id}/restore", response_model=PhotoResponse)
async def restore_photo(photo_id: int, service: PhotoService = Depends(_write_service)):
    try:
        return await service.restore_photo(photo_id)
    except PhotoNotFound:
        _raise_not_found()


@router.get("/{photo_id}/file")
async def get_photo_file(
    photo_id: int,
    size: str = Query("small", max_length=20),
    download: bool = Query(False),
    service: PhotoService = Depends(_service),
):
    try:
        path, filename, media_type = await service.resolve_file(photo_id, size)
    except PhotoNotFound:
        _raise_not_found()
    except PhotoServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    headers = {
        "Cache-Control": "private, max-age=86400",
        "Content-Disposition": _content_disposition(filename, download=download),
    }
    return FileResponse(path, media_type=media_type, headers=headers)


@router.post("/{photo_id}/analyze", response_model=PhotoJobResponse, status_code=201)
async def analyze_photo(
    photo_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission("photos.analyze")),
    db: AsyncSession = Depends(get_db),
):
    service = PhotoService(db, current_user)
    try:
        job = await service.request_analysis(photo_id)
    except PhotoNotFound:
        _raise_not_found()
    if get_settings().PHOTO_BACKGROUND_JOBS:
        background_tasks.add_task(run_pending_jobs_now)
    return job


@router.get("/{photo_id}/analysis", response_model=List[PhotoAnalysisResponse])
async def get_photo_analysis(photo_id: int, service: PhotoService = Depends(_service)):
    from sqlalchemy import select

    from app.models.photo import PhotoAnalysis

    try:
        await service.get_photo(photo_id)
    except PhotoNotFound:
        _raise_not_found()
    result = await service.db.execute(
        select(PhotoAnalysis)
        .where(PhotoAnalysis.photo_id == photo_id)
        .order_by(PhotoAnalysis.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{photo_id}/similar", response_model=PhotoSimilarResponse)
async def get_similar_photos(
    photo_id: int,
    limit: int = Query(12, ge=1, le=50),
    service: PhotoService = Depends(_service),
):
    """Photos les plus proches (similarité cosinus sur embeddings)."""
    try:
        photos, scores, indexed, provider = await service.find_similar(photo_id, limit)
    except PhotoNotFound:
        _raise_not_found()
    return PhotoSimilarResponse(
        items=[
            PhotoSimilarItem(photo=photo, score=round(score, 4))
            for photo, score in zip(photos, scores)
        ],
        indexed=indexed,
        provider=provider,
    )


@router.post(
    "/{photo_id}/embeddings", response_model=PhotoJobResponse, status_code=201
)
async def reindex_photo_embedding(
    photo_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission("photos.analyze")),
    db: AsyncSession = Depends(get_db),
):
    """Déclenche (ou force) la ré-indexation vectorielle d'une photo."""
    service = PhotoService(db, current_user)
    try:
        job = await service.request_embedding(photo_id)
    except PhotoNotFound:
        _raise_not_found()
    if get_settings().PHOTO_BACKGROUND_JOBS:
        background_tasks.add_task(run_pending_jobs_now)
    return job


@router.post(
    "/{photo_id}/faces", response_model=PhotoJobResponse, status_code=201
)
async def reindex_photo_faces(
    photo_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission("photos.analyze")),
    db: AsyncSession = Depends(get_db),
):
    """Déclenche (ou force) la détection des visages d'une photo.

    La ré-détection remplace les visages existants (les groupes qui ne
    contiendraient plus aucun visage sont nettoyés) ; les groupes nommés
    sont conservés, leurs visages désassociés.
    """
    if not get_settings().PHOTO_FACE_ENABLED:
        raise HTTPException(
            status_code=409, detail="Détection de visages désactivée"
        )
    service = PhotoService(db, current_user)
    try:
        job = await service.request_face_detection(photo_id)
    except PhotoNotFound:
        _raise_not_found()
    if get_settings().PHOTO_BACKGROUND_JOBS:
        background_tasks.add_task(run_pending_jobs_now)
    return job


@router.get("/{photo_id}/edits", response_model=List[PhotoEditResponse])
async def list_edits(photo_id: int, service: PhotoService = Depends(_service)):
    detail = await _detail_or_404(service, photo_id)
    return detail["edits"]


@router.post(
    "/{photo_id}/edits",
    response_model=PhotoEditResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_photo_edit(
    photo_id: int,
    data: PhotoEditCreate,
    service: PhotoService = Depends(_edit_service),
):
    try:
        photo = await service.get_photo(photo_id)
    except PhotoNotFound:
        _raise_not_found()
    try:
        edit = await create_edit(
            service.db,
            photo,
            kind=data.kind,
            params=data.params,
            name=data.name,
            created_by=service.current_user.id,
        )
    except PhotoEditUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None
    except PhotoEditError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if service.audit:
        await service.audit.log(
            action="edit",
            module="photos",
            user=service.current_user,
            object_type="photo_edit",
            object_id=str(edit.id),
            object_repr=f"{photo.original_filename} ({data.kind})",
        )
    return edit


@router.get("/{photo_id}/edits/{edit_id}/file")
async def get_edit_file(
    photo_id: int,
    edit_id: int,
    service: PhotoService = Depends(_service),
):
    try:
        path, filename, media_type = await service.resolve_edit_file(photo_id, edit_id)
    except PhotoNotFound:
        _raise_not_found()
    except PhotoServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/{photo_id}/revert", response_model=MessageResponse)
async def revert_photo(photo_id: int, service: PhotoService = Depends(_edit_service)):
    photo = await _owned(service, photo_id)
    deactivated = await revert_to_original(service.db, photo)
    return MessageResponse(message=f"Retour à l'original ({deactivated} version(s) désactivée(s))")


@router.get("/{photo_id}/tags", response_model=PhotoTagListResponse)
async def list_photo_tags(photo_id: int, service: PhotoService = Depends(_service)):
    detail = await _detail_or_404(service, photo_id)
    return PhotoTagListResponse(
        items=[PhotoTagResponse(**{**tag, "photo_count": 0}) for tag in detail["tags"]],
        total=len(detail["tags"]),
    )


@router.post("/{photo_id}/tags", response_model=PhotoTagResponse, status_code=201)
async def add_photo_tag(
    photo_id: int,
    data: PhotoTagCreate,
    service: PhotoService = Depends(_write_service),
):
    try:
        tag = await service.add_tag_to_photo(
            photo_id, data.name, data.category or "manual"
        )
    except PhotoNotFound:
        _raise_not_found()
    return PhotoTagResponse(
        id=tag.id,
        name=tag.name,
        slug=tag.slug,
        category=tag.category,
        photo_count=1,
    )


@router.delete("/{photo_id}/tags/{tag_id}", response_model=MessageResponse)
async def remove_photo_tag(
    photo_id: int,
    tag_id: int,
    service: PhotoService = Depends(_write_service),
):
    try:
        removed = await service.remove_tag_from_photo(photo_id, tag_id)
    except PhotoNotFound:
        _raise_not_found()
    if not removed:
        raise HTTPException(status_code=404, detail="Tag absent de la photo")
    return MessageResponse(message="Tag retiré")


# ================================ Helpers ================================

async def _detail_or_404(service: PhotoService, photo_id: int) -> dict:
    try:
        return await service.get_photo_detail(photo_id)
    except PhotoNotFound:
        _raise_not_found()


async def _owned(service: PhotoService, photo_id: int):
    try:
        return await service.get_photo(photo_id)
    except PhotoNotFound:
        _raise_not_found()
