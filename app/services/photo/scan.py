"""Scan / import idempotent d'un répertoire de stockage (Photos V3).

Le scan découvre les fichiers (images **et** vidéos) du backend courant
(local ou NAS monté) et crée les entrées ``Photo`` manquantes :

- **Idempotent** : un fichier déjà référencé (même chemin relatif) est
  simplement ignoré — aucun hash n'est recalculé dans ce cas.
- **Déduplication** : un fichier inconnu est hashé (SHA-256 streamé, mémoire
  bornée pour de gros volumes) ; s'il correspond à une photo déjà importée
  du même backend, il n'est pas importé deux fois — si son ancien chemin a
  disparu, la photo est considérée comme **déplacée / renommée** et son
  ``storage_path`` est mis à jour (aucune copie, aucun enregistrement).
- **Progressif** : parcours par ``os.walk`` + lots SQL — jamais toute la
  photothèque ni tous les chemins en mémoire.
- **Sans risque destructif** : aucun fichier n'est écrit hors du backend,
  aucun original n'est supprimé, et le marquage « manquant » (suppression
  logique, réversible, jamais de suppression fichier) n'a lieu qu'après un
  scan complet **et** si le stockage était ``available`` au début **et** à
  la fin. Un stockage ``unavailable`` interrompt tout, sans aucune
  suppression.

Exécution : job ``scan_import`` (jamais bloquant dans la requête HTTP).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo, PhotoJob, PhotoScanRun
from app.services.photo.jobs import PhotoJobError, enqueue_job, find_active_job
from app.services.photo.storage import PhotoStorageError, get_photo_storage, hash_file

logger = logging.getLogger(__name__)

# Extensions importées au scan : les formats déjà acceptés à l'upload plus
# HEIC/HEIF (photothèques iPhone) et les vidéos MOV/MP4 (référencées sans
# analyse — le décodage vidéo reste hors périmètre V3).
SUPPORTED_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".mov",
    ".mp4",
}

_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
}

VIDEO_EXTS = {".mov", ".mp4"}

# Taille des lots (fichiers) pour les requêtes SQL groupées.
BATCH_SIZE = 200
# Taille des pages pour la passe « fichiers manquants ».
MISSING_PAGE = 500


def is_video_ext(ext: str) -> bool:
    return ext in VIDEO_EXTS


def _naive(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo else dt


def _run_to_dict(run: PhotoScanRun) -> dict:
    started = _naive(run.started_at)
    finished = _naive(run.finished_at)
    return {
        "id": run.id,
        "backend": run.backend,
        "state": run.state,
        "detail": run.detail,
        "files_seen": run.files_seen,
        "created": run.created,
        "updated_paths": run.updated_paths,
        "missing_marked": run.missing_marked,
        "started_at": started.isoformat() if started else None,
        "finished_at": finished.isoformat() if finished else None,
    }


async def _finish_run(
    db: AsyncSession,
    run_id: int,
    *,
    state: str,
    detail: str | None = None,
    files_seen: int = 0,
    created: int = 0,
    updated_paths: int = 0,
    missing_marked: int = 0,
) -> dict:
    run = await db.get(PhotoScanRun, run_id)
    run.state = state
    run.detail = detail
    run.files_seen = files_seen
    run.created = created
    run.updated_paths = updated_paths
    run.missing_marked = missing_marked
    run.finished_at = datetime.now()
    await db.commit()
    return _run_to_dict(run)


async def _process_batch(
    db: AsyncSession,
    *,
    owner_id: int,
    backend_name: str,
    batch: list[tuple[Path, str]],
    backend_obj,
) -> tuple[int, int]:
    """Traite un lot : références existantes ignorées (idempotence, aucun
    hash), nouveaux fichiers hashés et dédupliqués, déplacés mis à jour,
    nouveaux importés + job ``ingest``.

    Retourne (créés, chemins mis à jour)."""
    if not batch:
        return 0, 0

    rels = [rel for _, rel in batch]
    result = await db.execute(
        select(Photo).where(
            Photo.storage_backend == backend_name,
            Photo.storage_path.in_(rels),
        )
    )
    known = {photo.storage_path: photo for photo in result.scalars().all()}

    # Uniquement les fichiers inconnus sont hashés (coût disque borné).
    # Tri des entrées de répertoire : le résultat d'un scan doit être
    # déterministe (le premier fichier d'un contenu donné devient le
    # candidat référent d'un contenu dupliqué dans le même lot).
    hash_of: dict[str, tuple[Path, str]] = {}
    for path, rel in batch:
        if rel in known:
            continue
        try:
            digest = hash_file(path)
        except OSError as exc:
            logger.warning("[PHOTO-SCAN] fichier illisible ignoré (%s): %s", rel, exc)
            continue
        if digest in hash_of:
            # Contenu déjà rencontré dans CE lot : non référencé (encore),
            # il sera ignoré — un seul exemplaire suffit.
            continue
        hash_of[digest] = (path, rel)

    moves: list[tuple[Photo, str]] = []
    if hash_of:
        dup_result = await db.execute(
            select(Photo).where(
                Photo.owner_id == owner_id,
                Photo.storage_backend == backend_name,
                Photo.content_hash.in_(list(hash_of)),
            )
        )
        for photo in dup_result.scalars().all():
            pending = hash_of.get(photo.content_hash)
            if pending is None:
                continue
            # Fichier identique déjà référencé ailleurs : déplacé/renommé
            # (ancien chemin disparu) ou copie (ancien présent → ignore).
            try:
                old_exists = backend_obj.original_path(photo.storage_path).is_file()
            except PhotoStorageError:
                old_exists = False
            if old_exists:
                hash_of.pop(photo.content_hash, None)
                continue
            moves.append((photo, pending[1]))
            hash_of.pop(photo.content_hash, None)

    updated_paths = 0
    for photo, rel in moves:
        photo.storage_path = rel
        updated_paths += 1
        logger.info("[PHOTO-SCAN] photo %s déplacée/renommée → %s", photo.id, rel)

    created = 0
    for digest, (path, rel) in hash_of.items():
        try:
            stat = path.stat()
        except OSError as exc:
            logger.warning("[PHOTO-SCAN] stat impossible (%s): %s", rel, exc)
            continue
        ext = path.suffix.lower()
        photo = Photo(
            owner_id=owner_id,
            title=None,
            original_filename=path.name[:500],
            storage_path=rel,
            storage_backend=backend_name,
            mime_type=_MIME_BY_EXT.get(ext, "application/octet-stream"),
            byte_size=stat.st_size,
            taken_at=datetime.fromtimestamp(stat.st_mtime),
            content_hash=digest,
            status="pending",
            analysis_status="pending",
        )
        db.add(photo)
        await db.flush()
        # Même chaîne d'ingest qu'un upload : miniatures, analyse, visages.
        await enqueue_job(db, type="ingest", photo_id=photo.id, commit=False)
        created += 1

    await db.commit()
    return created, updated_paths


async def _mark_missing(db: AsyncSession, *, backend_name: str, backend_obj) -> int:
    """Passe « fichiers manquants » : pour chaque photo non supprimée du
    backend, un ``storage_path`` qui n'existe plus sur disque → suppression
    logique (``is_deleted``). **Aucun fichier n'est jamais touché.**

    À n'appeler qu'après un scan complet avec stockage ``available``."""
    missing = 0
    last_id = 0
    while True:
        result = await db.execute(
            select(Photo.id, Photo.storage_path)
            .where(
                Photo.storage_backend == backend_name,
                Photo.is_deleted.is_(False),
                Photo.id > last_id,
            )
            .order_by(Photo.id)
            .limit(MISSING_PAGE)
        )
        rows = result.all()
        if not rows:
            break
        for photo_id, rel in rows:
            last_id = photo_id
            try:
                exists = backend_obj.original_path(rel).is_file()
            except PhotoStorageError:
                continue
            if exists:
                continue
            photo = await db.get(Photo, photo_id)
            photo.is_deleted = True
            photo.deleted_at = datetime.now()
            missing += 1
            # Un job d'ingest en attente ne doit pas tourner pour rien.
            await db.execute(
                update(PhotoJob)
                .where(
                    PhotoJob.photo_id == photo_id,
                    PhotoJob.status == "pending",
                )
                .values(status="failed", error="original manquant (scan)")
            )
            logger.warning(
                "[PHOTO-SCAN] photo %s : original manquant (%s) → marquée supprimée",
                photo_id,
                rel,
            )
        await db.commit()
    return missing


async def run_scan(
    db: AsyncSession,
    *,
    owner_id: int | None,
    backend: str | None = None,
    mark_missing: bool = True,
) -> dict:
    """Exécute un scan complet du backend. Retourne l'état persisté.

    ``state`` : ``available`` (scan fait), ``unavailable`` / ``error``
    (interrompu, aucune suppression)."""
    settings = get_settings()
    storage = get_photo_storage()
    backend_name = (backend or settings.PHOTO_STORAGE_BACKEND or "local").strip()

    if owner_id is None:
        raise PhotoJobError("scan_import : propriétaire (owner_id) manquant")

    try:
        backend_obj = storage.backend(backend_name)
    except PhotoStorageError as exc:
        logger.error("[PHOTO-SCAN] backend invalide %r: %s", backend_name, exc)
        raise PhotoJobError(f"Backend invalide: {exc}") from exc

    run = PhotoScanRun(owner_id=owner_id, backend=backend_name, state="running")
    db.add(run)
    await db.flush()
    run_id = run.id
    await db.commit()

    files_seen = created = updated_paths = 0
    try:
        status = backend_obj.check()
        if status.state != "available":
            logger.warning(
                "[PHOTO-SCAN] stockage %s %s — scan interrompu, aucune suppression",
                backend_name,
                status.state,
            )
            return await _finish_run(
                db, run_id, state=status.state, detail=status.detail
            )

        root = backend_obj.scan_root
        batch: list[tuple[Path, str]] = []

        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in sorted(filenames):
                path = Path(dirpath) / filename
                if path.is_symlink():
                    # Jamais de symlink : évite de référencer (ou de lire)
                    # une cible hors de la racine de stockage.
                    continue
                if path.suffix.lower() not in SUPPORTED_EXTS:
                    continue
                try:
                    rel = path.relative_to(root).as_posix()
                except ValueError:
                    continue
                files_seen += 1
                batch.append((path, rel))
                if len(batch) >= BATCH_SIZE:
                    c, u = await _process_batch(
                        db,
                        owner_id=owner_id,
                        backend_name=backend_name,
                        batch=batch,
                        backend_obj=backend_obj,
                    )
                    created += c
                    updated_paths += u
                    batch = []
        if batch:
            c, u = await _process_batch(
                db,
                owner_id=owner_id,
                backend_name=backend_name,
                batch=batch,
                backend_obj=backend_obj,
            )
            created += c
            updated_paths += u

        missing = 0
        if mark_missing:
            # Le stockage a pu tomber en plein scan : dans le doute, aucune
            # suppression logique.
            status = backend_obj.check()
            if status.state != "available":
                logger.warning(
                    "[PHOTO-SCAN] stockage %s %s après scan — marquage manquant annulé",
                    backend_name,
                    status.state,
                )
                return await _finish_run(
                    db,
                    run_id,
                    state=status.state,
                    detail=status.detail,
                    files_seen=files_seen,
                    created=created,
                    updated_paths=updated_paths,
                )
            missing = await _mark_missing(
                db, backend_name=backend_name, backend_obj=backend_obj
            )

        detail = f"scan terminé — {files_seen} fichier(s) vu(s)"
        if not files_seen:
            detail += " (répertoire vide)"
        logger.info(
            "[PHOTO-SCAN] %s: %s | créés=%s déplacés=%s manquants=%s",
            backend_name,
            detail,
            created,
            updated_paths,
            missing,
        )
        return await _finish_run(
            db,
            run_id,
            state="available",
            detail=detail,
            files_seen=files_seen,
            created=created,
            updated_paths=updated_paths,
            missing_marked=missing,
        )
    except PhotoJobError:
        await _finish_run(
            db,
            run_id,
            state="error",
            detail="erreur de scan",
            files_seen=files_seen,
            created=created,
            updated_paths=updated_paths,
        )
        raise
    except Exception as exc:  # noqa: BLE001 - état persisté avant re-raise
        logger.exception("[PHOTO-SCAN] scan interrompu: %s", exc)
        await _finish_run(
            db,
            run_id,
            state="error",
            detail=str(exc)[:500],
            files_seen=files_seen,
            created=created,
            updated_paths=updated_paths,
        )
        raise PhotoJobError(f"Scan interrompu: {exc}") from exc


async def last_scan_run(db: AsyncSession, backend: str) -> PhotoScanRun | None:
    result = await db.execute(
        select(PhotoScanRun)
        .where(PhotoScanRun.backend == backend)
        .order_by(PhotoScanRun.started_at.desc(), PhotoScanRun.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def maybe_schedule_scan(db: AsyncSession) -> None:
    """Monitoring périodique (appelé par la boucle de jobs) : enfile un scan
    si ``PHOTO_NAS_SCAN_ENABLED`` et si le dernier scan est trop ancien.

    Le propriétaire du scan = celui du dernier scan (au premier scan
    manuel, pas d'attribution hasardeuse d'une photothèque à un utilisateur
    non déterminé)."""
    settings = get_settings()
    if not settings.PHOTO_NAS_SCAN_ENABLED:
        return
    backend_name = (settings.PHOTO_STORAGE_BACKEND or "local").strip()

    last = await last_scan_run(db, backend_name)
    if last is None:
        logger.debug(
            "[PHOTO-SCAN] scan auto en attente d'un premier scan manuel (%s)",
            backend_name,
        )
        return
    interval = max(int(settings.PHOTO_NAS_SCAN_INTERVAL_SECONDS), 30)
    started = _naive(last.started_at)
    if started and datetime.now() - started < timedelta(seconds=interval):
        return

    existing = await find_active_job(db, type="scan_import", photo_id=None)
    if existing is not None:
        return
    await enqueue_job(
        db,
        type="scan_import",
        photo_id=None,
        payload={"owner_id": last.owner_id, "backend": backend_name},
    )
    logger.info("[PHOTO-SCAN] scan automatique %s mis en file", backend_name)
