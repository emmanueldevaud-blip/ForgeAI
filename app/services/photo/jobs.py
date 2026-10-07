"""File de tâches d'arrière-plan du module Photos.

Mécanisme repris du pattern « job persistant en base » (type
``DevelopmentTask``) : les jobs sont écrits par les endpoints puis consommés
soit par la boucle ``photo_job_loop`` (lifespan), soit immédiatement après la
réponse via ``BackgroundTasks`` si ``PHOTO_BACKGROUND_JOBS`` est actif.

Le traitement lourd (Pillow) s'exécute dans un thread pour ne jamais bloquer
la boucle d'événements — la galerie reste réactive pendant l'import.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo, PhotoFace, PhotoJob, PhotoPlace
from app.services.photo.storage import PhotoStorageError, get_photo_storage

logger = logging.getLogger(__name__)

JobHandler = Callable[[AsyncSession, Photo | None, dict], Awaitable[None]]

# Un job 'running' plus ancien que ce délai est considéré comme orphelin
# (processus mort en plein traitement) et re-mis en file : sans ça, la photo
# resterait « pending » à vie après un crash. Large marge par rapport à la
# durée réelle d'un ingest pour ne jamais reprendre un job encore vivant.
STALE_RUNNING_AFTER = timedelta(minutes=15)


def _utcnow() -> datetime:
    # Horloge alignée sur CURRENT_TIMESTAMP (UTC) des bases MySQL / SQLite.
    return datetime.now(UTC).replace(tzinfo=None)


class PhotoJobError(Exception):
    pass


async def enqueue_job(
    db: AsyncSession,
    *,
    type: str,
    photo_id: int | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> PhotoJob:
    """Ajoute un job à la file.

    ``commit=False`` : le job est simplement flushé, pour que l'appelant
    l'enregistre dans SA transaction (photo + job atomiques à l'import).
    """
    job = PhotoJob(
        photo_id=photo_id,
        type=type,
        status="pending",
        payload_json=payload or {},
        max_attempts=get_settings().PHOTO_JOB_MAX_ATTEMPTS,
        # Petite tolérance de barrière : le job doit être immédiatement
        # consommable même si l'horloge applicative avance d'une fraction
        # par rapport à CURRENT_TIMESTAMP (secondes tronquées).
        available_at=_utcnow() - timedelta(seconds=1),
    )
    db.add(job)
    if commit:
        await db.commit()
        await db.refresh(job)
    else:
        await db.flush()
    return job


async def find_active_job(
    db: AsyncSession, *, type: str, photo_id: int | None
) -> PhotoJob | None:
    """Job en attente ou en cours pour (type, photo) — anti-doublons."""
    result = await db.execute(
        select(PhotoJob)
        .where(
            PhotoJob.type == type,
            PhotoJob.photo_id == photo_id,
            PhotoJob.status.in_(("pending", "running")),
        )
        .order_by(PhotoJob.created_at)
        .limit(1)
    )
    return result.scalars().first()


async def enqueue_job_unique(
    db: AsyncSession,
    *,
    type: str,
    photo_id: int | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> PhotoJob:
    """Ajoute un job sauf si un job du même type est déjà en file.

    Retourne le job existant ou le job créé : jamais deux jobs « analyze »
    ou « embedding » simultanés pour une même photo (double travail et
    écritures concurrentes sur la même ligne d'analyse).
    """
    existing = await find_active_job(db, type=type, photo_id=photo_id)
    if existing is not None:
        if commit:
            await db.commit()
        return existing
    return await enqueue_job(
        db, type=type, photo_id=photo_id, payload=payload, commit=commit
    )


# ------------------------------------------------------------------ ingest

async def _resolve_place(db: AsyncSession, photo: Photo) -> None:
    """Associe la photo à une cellule GPS (cache en base, pas d'appel par photo)."""
    if photo.gps_latitude is None or photo.gps_longitude is None:
        return
    lat_cell = round(photo.gps_latitude, 2)
    lon_cell = round(photo.gps_longitude, 2)
    result = await db.execute(
        select(PhotoPlace).where(
            PhotoPlace.lat_cell == lat_cell, PhotoPlace.lon_cell == lon_cell
        )
    )
    place = result.scalar_one_or_none()
    if place is None:
        place = PhotoPlace(lat_cell=lat_cell, lon_cell=lon_cell, label="", source="coords")
        db.add(place)
        await db.flush()
    photo.place_id = place.id


async def _store_thumbnails(db: AsyncSession, photo: Photo, results: list[dict]) -> None:
    """Remplace les miniatures d'une photo (ré-ingestion, même logique V1)."""
    from app.models.photo import PhotoThumbnail

    existing = await db.execute(
        select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo.id)
    )
    old_thumbs = existing.scalars().all()
    for row in old_thumbs:
        await db.delete(row)
    if old_thumbs:
        # Flush intermédiaire : SQLA émet les INSERT avant les DELETE pour une
        # même table (pas de dépendance de clé étrangère), ce qui violerait la
        # contrainte UNIQUE (photo_id, size) sur une ré-ingestion.
        await db.flush()
    for item in results:
        db.add(
            PhotoThumbnail(
                photo_id=photo.id,
                size=item["size"],
                # Relatif à la racine des miniatures (avec le dossier photo).
                storage_path=f"{photo.id}/{item['storage_path']}",
                width=item["width"],
                height=item["height"],
                byte_size=item["byte_size"],
            )
        )


async def _generate_thumbnails_safe(
    original_path, thumbs_dir
) -> tuple[list[dict] | None, str | None]:
    """Génération protégée : une miniature impossible (HEIC corrompu,
    ffmpeg absent, codec non supporté, fichier parti…) **ne fait jamais
    échouer l'import** — elle dégrade en (None, raison journalisée)."""
    from app.services.photo.thumbnails import generate_thumbnails, parse_thumbnail_sizes

    try:
        results = await asyncio.to_thread(
            generate_thumbnails,
            original_path,
            thumbs_dir,
            parse_thumbnail_sizes(),
        )
    except Exception as exc:  # noqa: BLE001 - l'import doit survivre
        logger.warning(
            "[PHOTO] miniatures impossibles pour %s: %s", original_path.name, exc
        )
        return None, str(exc)[:300] or type(exc).__name__
    if not results:
        return None, "aucune taille de miniature générée"
    return results, None


async def _ingest(db: AsyncSession, photo: Photo | None, payload: dict) -> None:
    if photo is None:
        raise PhotoJobError("Photo introuvable")

    from app.services.photo.metadata import MetadataError, extract_metadata
    from app.services.photo.scan import is_video_ext

    storage = get_photo_storage()
    # Backend de la photo (colonne), jamais le backend courant : changer la
    # configuration ne doit pas rendre une photo existante inaccessible.
    try:
        original_path = storage.backend_for_photo(photo).original_path(
            photo.storage_path
        )
    except PhotoStorageError as exc:
        raise PhotoJobError(f"Backend de la photo non configuré: {exc}") from exc
    if not original_path.is_file():
        raise PhotoJobError("Fichier original introuvable")

    ext = original_path.suffix.lower()
    thumbs_dir = storage.thumbs_root / str(photo.id)

    if photo.mime_type.startswith("video/") or is_video_ext(ext):
        # Vidéo (import NAS) : frame via ffmpeg si disponible. L'analyse
        # image / visages V1-V2 ne s'exécute jamais sur une vidéo.
        results, thumb_error = await _generate_thumbnails_safe(
            original_path, thumbs_dir
        )
        if results:
            await _store_thumbnails(db, photo, results)
            photo.width = results[0].get("source_width") or photo.width
            photo.height = results[0].get("source_height") or photo.height
            photo.error = None
        else:
            # Une miniature absente ne transforme pas une vidéo valide en
            # import échoué : la vidéo reste servable en original.
            photo.error = f"Vidéo importée, miniature indisponible : {thumb_error}"
        photo.status = "ready"
        photo.analysis_status = "skipped"
        await db.commit()
        return

    data = await asyncio.to_thread(original_path.read_bytes)
    try:
        meta = await asyncio.to_thread(extract_metadata, data)
    except MetadataError:
        if ext in {".heic", ".heif"}:
            # pillow-heif absent ou HEIC corrompu : l'original reste la
            # source de vérité (inchangé) et la photo est référencée,
            # sans miniatures ni analyse.
            logger.warning("[PHOTO] HEIC non décodable: %s (%s)", photo.id, original_path.name)
            photo.status = "ready"
            photo.analysis_status = "skipped"
            photo.error = (
                "HEIC non décodable (pillow-heif absent ou fichier corrompu) : "
                "miniatures/analyse indisponibles"
            )
            await db.commit()
            return
        raise

    photo.width = meta["width"]
    photo.height = meta["height"]
    if meta.get("taken_at"):
        photo.taken_at = meta["taken_at"]
    if meta.get("gps"):
        photo.gps_latitude, photo.gps_longitude = meta["gps"]
    photo.camera_make = meta.get("camera_make") or photo.camera_make
    photo.camera_model = meta.get("camera_model") or photo.camera_model
    photo.exif_json = meta.get("exif") or photo.exif_json
    await _resolve_place(db, photo)

    # Miniatures (HEIC compris via pillow-heif) : un échec ne fait jamais
    # échouer l'import — la photo reste « ready » avec l'erreur renseignée.
    results, thumb_error = await _generate_thumbnails_safe(original_path, thumbs_dir)
    if results:
        await _store_thumbnails(db, photo, results)
        photo.status = "ready"
        photo.error = None
    else:
        photo.status = "ready"
        photo.error = f"Miniatures indisponibles : {thumb_error}"
        # Pas de pipeline d'analyse sans miniature exploitable.
        if photo.analysis_status == "pending":
            photo.analysis_status = "skipped"
    await db.commit()

    if results:
        settings = get_settings()
        analysis_queued = False
        if settings.PHOTO_ANALYSIS_ENABLED and photo.analysis_status == "pending":
            await enqueue_job_unique(db, type="analyze", photo_id=photo.id)
            analysis_queued = True
        elif settings.PHOTO_EMBEDDING_ENABLED:
            # Analyse désactivée : on passe directement à l'indexation vectorielle.
            await enqueue_job_unique(db, type="embedding", photo_id=photo.id)
        if settings.PHOTO_FACE_ENABLED and not analysis_queued:
            # Chaîne INGEST → ANALYZE → FACE_DETECT : si l'analyse est en file,
            # c'est elle qui enchaîne la détection (sinon on l'enfile ici —
            # photo déjà analysée ou analyse désactivée).
            await enqueue_job_unique(db, type="face_detect", photo_id=photo.id)


async def _analyze(db: AsyncSession, photo: Photo | None, payload: dict) -> None:
    if photo is None:
        raise PhotoJobError("Photo introuvable")
    from app.services.photo.analysis import run_analysis

    analysis = await run_analysis(db, photo)
    if analysis.status == "failed":
        # L'erreur est consignée dans photo_analyses ; on lève ici pour que
        # le mécanisme de retry (backoff, max_attempts) s'applique.
        raise PhotoJobError(analysis.error or "Analyse échouée")

    settings = get_settings()
    if settings.PHOTO_FACE_ENABLED:
        # Chaîne ANALYZE → FACE_DETECT (dédoublement : un job déjà en file
        # est réutilisé, jamais deux détections simultanées pour la photo).
        await enqueue_job_unique(db, type="face_detect", photo_id=photo.id)
    if settings.PHOTO_EMBEDDING_ENABLED:
        await enqueue_job_unique(db, type="embedding", photo_id=photo.id)


async def _embedding(db: AsyncSession, photo: Photo | None, payload: dict) -> None:
    if photo is None:
        raise PhotoJobError("Photo introuvable")
    from app.services.photo.embeddings import run_embedding

    await run_embedding(db, photo, force=bool((payload or {}).get("force")))


async def _face_detect(db: AsyncSession, photo: Photo | None, payload: dict) -> None:
    """Détection de visages : miniature uniquement, original intact."""
    if photo is None:
        raise PhotoJobError("Photo introuvable")
    if not get_settings().PHOTO_FACE_ENABLED:
        # Désactivé entre-temps : rien à faire, le job se termine proprement.
        return
    from app.services.photo.face_detection import run_face_detection
    from app.services.photo.face_grouping import cleanup_empty_auto_people

    force = bool((payload or {}).get("force"))
    state = await run_face_detection(db, photo, force=force)
    if state.status == "failed":
        # Erreur consignée (kind="faces") ; on lève pour le retry.
        raise PhotoJobError(state.error or "Détection de visages échouée")

    # Une ré-detection a pu vider d'anciens groupes anonymes : nettoyage.
    await cleanup_empty_auto_people(db, photo.owner_id)
    await db.commit()

    face_count = state.result_json.get("faces", 0) if state.result_json else 0
    if face_count and get_settings().PHOTO_FACE_GROUPING_ENABLED:
        await enqueue_job_unique(db, type="face_embedding", photo_id=photo.id)


async def _face_embedding(db: AsyncSession, photo: Photo | None, payload: dict) -> None:
    """Indexation des visages : affectation des visages non groupés.

    Les embeddings sont produits par le détecteur au moment de la
    détection (protocol ``FaceDetectionProvider``) ; cette étape vérifie
    qu'il reste des visages non affectés pour ce propriétaire puis lance
    le regroupement (centroïdes, groupes anonymes).
    """
    if photo is None:
        raise PhotoJobError("Photo introuvable")
    settings = get_settings()
    if not settings.PHOTO_FACE_ENABLED or not settings.PHOTO_FACE_GROUPING_ENABLED:
        return
    from sqlalchemy import exists

    from app.services.photo.face_grouping import group_owner_faces

    has_unassigned = (
        await db.execute(
            select(Photo.id)
            .where(
                Photo.id == photo.id,
                exists().where(
                    PhotoFace.photo_id == Photo.id,
                    PhotoFace.person_id.is_(None),
                    PhotoFace.embedding_json.is_not(None),
                ),
            )
            .limit(1)
        )
    ).first()
    if has_unassigned is None:
        # Rien à regrouper : évite un O(n·k) complet à chaque photo.
        return
    await group_owner_faces(db, photo.owner_id)


async def _scan_import(db: AsyncSession, photo: Photo | None, payload: dict) -> None:
    """Scan/import d'un répertoire de stockage (V3) — job global (photo_id
    nul), propriétaire porté par le payload. Un état non ``available`` est
    un échec (retries + ``failed``) : **aucune suppression** n'a eu lieu."""
    if photo is not None:
        raise PhotoJobError("scan_import ne porte pas de photo")
    from app.services.photo.scan import run_scan

    payload = payload or {}
    result = await run_scan(
        db,
        owner_id=payload.get("owner_id"),
        backend=payload.get("backend"),
        mark_missing=bool(payload.get("mark_missing", True)),
    )
    if result["state"] != "available":
        detail = result.get("detail") or ""
        raise PhotoJobError(f"Scan interrompu ({result['state']}): {detail}")


HANDLERS: dict[str, JobHandler] = {
    "ingest": _ingest,
    "analyze": _analyze,
    "embedding": _embedding,
    "face_detect": _face_detect,
    "face_embedding": _face_embedding,
    "scan_import": _scan_import,
}


async def process_photo_jobs(
    db: AsyncSession, *, limit: int | None = None, types: list[str] | None = None
) -> int:
    """Exécute les jobs en attente. Retourne le nombre de jobs traités."""
    settings = get_settings()
    batch = limit or settings.PHOTO_JOB_BATCH

    query = select(PhotoJob).where(
        PhotoJob.status == "pending",
        PhotoJob.available_at <= func.now(),
    )
    if types:
        query = query.where(PhotoJob.type.in_(types))
    query = query.order_by(PhotoJob.created_at).limit(batch)

    result = await db.execute(query)
    jobs = list(result.scalars().all())
    processed = 0

    # Reprise des jobs orphelins : un 'running' trop ancien vient d'un
    # processus mort en pleine exécution (pas de timeout par job).
    stale = await db.execute(
        update(PhotoJob)
        .where(
            PhotoJob.status == "running",
            PhotoJob.started_at < _utcnow() - STALE_RUNNING_AFTER,
        )
        # Même tolérance de barrière qu'à la création : available_at porte
        # des micros secondes mais func.now() est tronqué à la seconde.
        .values(status="pending", available_at=_utcnow() - timedelta(seconds=1))
    )
    if stale.rowcount:
        await db.commit()
        logger.warning(
            "[PHOTO-JOBS] %s job(s) 'running' orphelin(s) remis en file",
            stale.rowcount,
        )
        result = await db.execute(query)
        jobs = list(result.scalars().all())

    for job in jobs:
        claim = await db.execute(
            update(PhotoJob)
            .where(PhotoJob.id == job.id, PhotoJob.status == "pending")
            .values(
                status="running",
                attempts=PhotoJob.attempts + 1,
                started_at=_utcnow(),
            )
        )
        if claim.rowcount == 0:
            continue
        # Le claim (status='running' + attempts+1) est commité AVANT
        # l'exécution : sinon un handler qui casse la transaction (flush ou
        # commit en échec) l'annule avec, les tentatives ne sont jamais
        # persistées et le même job est rejoué indéfiniment.
        await db.commit()

        handler = HANDLERS.get(job.type)
        # Identifiants lus AVANT l'exécution : un handler dont le flush casse
        # la transaction expire les instances, leur accès lèverait alors
        # PendingRollbackError avant même le rollback.
        job_id = job.id
        job_type = job.type
        photo_id = job.photo_id
        payload = job.payload_json or {}
        photo = None
        if photo_id:
            photo = await db.get(Photo, photo_id)
        try:
            if handler is None:
                raise PhotoJobError(f"Type de job inconnu: {job_type}")
            await handler(db, photo, payload)
            job.status = "done"
            job.finished_at = _utcnow()
            job.error = None
        except Exception as exc:  # noqa: BLE001 - un job en échec ne tue pas la boucle
            # La session peut être en échec (flush/commit annulé) : on repart
            # d'un état propre pour que l'état du job soit bien persisté.
            await db.rollback()
            job = await db.get(PhotoJob, job_id, populate_existing=True) or job
            job.error = f"{type(exc).__name__}: {exc}"
            if job.attempts >= job.max_attempts:
                job.status = "failed"
                job.finished_at = _utcnow()
                if photo is not None and job_type == "ingest":
                    # ``photo`` est expiré après rollback : rechargement explicite.
                    photo = await db.get(Photo, photo_id, populate_existing=True)
                    photo.status = "failed"
                    photo.error = job.error
                logger.warning(
                    "[PHOTO-JOBS] job=%s photo=%s échec définitif: %s",
                    job_type,
                    photo_id,
                    job.error,
                )
            else:
                # Retry avec backoff simple.
                job.status = "pending"
                job.available_at = _utcnow() + timedelta(seconds=30 * job.attempts)
                logger.warning(
                    "[PHOTO-JOBS] job=%s tentative %s/%s: %s",
                    job_type,
                    job.attempts,
                    job.max_attempts,
                    job.error,
                )
        await db.commit()
        processed += 1

    return processed


async def run_pending_jobs_now() -> None:
    """Traite les jobs avec une session dédiée (post-réponse HTTP)."""
    from app.db.session import get_db_context

    try:
        async with get_db_context() as db:
            await process_photo_jobs(db)
    except Exception:  # noqa: BLE001
        logger.exception("[PHOTO-JOBS] exécution immédiate impossible")
