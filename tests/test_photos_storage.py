"""Tests V3 — stockage des originaux (backends local/NAS) et scan/import.

Le « NAS » des tests est un répertoire temporaire (ForgeAI ne gère ni SMB
ni NFS : seul un chemin monté est utilisé). Aucun test ne touche à la
base de production ni à un vrai montage.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from test_photos import (
    create_limited_user,
    drain_jobs,
    login,
    make_image_bytes,
    upload_photo,
)

from app.core.config import get_settings
from app.models.photo import Photo, PhotoJob, PhotoScanRun
from app.services.photo import storage as storage_mod
from app.services.photo.scan import maybe_schedule_scan, run_scan
from app.services.photo.storage import (
    NasFilesystemStorage,
    PhotoStorageError,
    get_photo_storage,
)

pytestmark = pytest.mark.asyncio


# ================================ Helpers ================================

@pytest.fixture(autouse=True)
def _reset_photo_storage():
    """Jamais de singleton photo-storage laissé pointant sur un NAS de test
    après la fin d'un test."""
    yield
    storage_mod._storage = None


def configure_storage(
    monkeypatch,
    *,
    backend: str | None = "nas",
    nas_path: Path | None = None,
    scan_enabled: bool | None = None,
    scan_interval: int | None = None,
):
    settings = get_settings()
    if backend is not None:
        monkeypatch.setattr(settings, "PHOTO_STORAGE_BACKEND", backend)
    if nas_path is not None:
        monkeypatch.setattr(settings, "PHOTO_NAS_PATH", str(nas_path))
    if scan_enabled is not None:
        monkeypatch.setattr(settings, "PHOTO_NAS_SCAN_ENABLED", scan_enabled)
    if scan_interval is not None:
        monkeypatch.setattr(settings, "PHOTO_NAS_SCAN_INTERVAL_SECONDS", scan_interval)
    storage_mod._storage = None
    return get_photo_storage()


def mount_nas(tmp_path: Path, *, empty: bool = False) -> Path:
    root = tmp_path / "nas"
    root.mkdir(parents=True, exist_ok=True)
    if not empty:
        (root / ".keep").write_bytes(b"mounted")
    return root


def write_nas(root: Path, rel: str, data: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


async def scan_import(db, owner_id: int, *, mark_missing: bool = True, backend: str = "nas"):
    return await run_scan(
        db, owner_id=owner_id, backend=backend, mark_missing=mark_missing
    )


async def photo_rows(db) -> list[Photo]:
    return list((await db.execute(select(Photo))).scalars().all())


# ================================ Backends ================================

async def test_local_backend_check_and_paths(tmp_path, monkeypatch):
    storage = configure_storage(monkeypatch, backend="local")
    status = storage.check("local")
    assert status.state == "available"
    rel = storage.save_original(7, "abc123", ".jpg", b"data")
    assert rel.startswith("7/")
    path = storage.original_path(rel)
    assert path.is_file()
    assert storage.backend_for_photo(Photo(storage_path=rel, storage_backend="local"))
    storage.delete_original(rel)
    assert not path.exists()


async def test_backend_unknown_and_nas_without_path(monkeypatch):
    storage = configure_storage(monkeypatch, backend="local", nas_path="")
    with pytest.raises(PhotoStorageError):
        storage.backend("nas")
    with pytest.raises(PhotoStorageError):
        storage.backend("s3")
    with pytest.raises(PhotoStorageError):
        NasFilesystemStorage("")


async def test_nas_check_states(tmp_path, monkeypatch):
    missing = tmp_path / "not-mounted"
    storage = configure_storage(monkeypatch, nas_path=missing)
    assert storage.check("nas").state == "unavailable"

    empty = mount_nas(tmp_path, empty=True)
    storage = configure_storage(monkeypatch, nas_path=empty)
    # Répertoire vide alors qu'un montage est attendu → indisponible.
    assert storage.check("nas").state == "unavailable"

    full = mount_nas(tmp_path, empty=False)
    storage = configure_storage(monkeypatch, nas_path=full)
    assert storage.check("nas").state == "available"
    assert storage.check("nas").path == str(full)


async def test_path_traversal_rejected_and_unicode_accepted(tmp_path, monkeypatch):
    storage = configure_storage(monkeypatch, nas_path=mount_nas(tmp_path))
    for evil in (
        "../etc/passwd",
        "a/../../b.jpg",
        "/etc/passwd",
        "a\\b.jpg",
        "a\x00b.jpg",
        "",
        "dir//x.jpg",
        "./x.jpg",
    ):
        with pytest.raises(PhotoStorageError):
            storage.original_path(evil)
    # Espaces et accents (photothèque réelle) acceptés.
    ok = storage.original_path("photos de l'été/café 2026.jpg")
    assert str(ok).endswith("photos de l'été/café 2026.jpg")


async def test_nas_delete_original_is_never_executed(tmp_path, monkeypatch):
    """Jamais de suppression d'original NAS (règle V3)."""
    root = mount_nas(tmp_path)
    path = write_nas(root, "1/2026/10/abc.jpg", b"original")
    backend = NasFilesystemStorage(str(root))
    backend.delete_original("1/2026/10/abc.jpg")
    assert path.is_file()


# ================================ Upload en mode NAS ================================

async def test_upload_uses_nas_backend(client, db_session, admin_user, admin_headers, tmp_path, monkeypatch):
    root = mount_nas(tmp_path)
    storage = configure_storage(monkeypatch, nas_path=root)
    assert storage.default_backend_name == "nas"

    data = make_image_bytes()
    response = await upload_photo(client, admin_headers, data, filename="nas-upload.jpg")
    assert response.status_code == 201, response.text
    photo_id = response.json()["items"][0]["id"]

    row = await db_session.get(Photo, photo_id)
    assert row.storage_backend == "nas"
    assert not row.storage_path.startswith("/")
    path = root / row.storage_path
    assert path.is_file()
    assert path.read_bytes() == data
    # L'original n'est PAS écrit dans le stockage local.
    local = storage.original_path(row.storage_path, "local")
    assert not local.exists()

    await drain_jobs(db_session)
    await db_session.refresh(row)
    assert row.status == "ready"

    # Lecture via l'endpoint fichier : le backend suit la photo.
    file_response = await client.get(
        f"/photos/{photo_id}/file?size=original", headers=admin_headers
    )
    assert file_response.status_code == 200


async def test_delete_photo_keeps_nas_original(client, db_session, admin_headers, tmp_path, monkeypatch):
    root = mount_nas(tmp_path)
    configure_storage(monkeypatch, nas_path=root)
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    row = await db_session.get(Photo, photo_id)
    original = root / row.storage_path
    assert original.is_file()

    deleted = await client.delete(f"/photos/{photo_id}", headers=admin_headers)
    assert deleted.status_code == 204, deleted.text

    await db_session.refresh(row)
    assert row.is_deleted is True
    assert original.is_file(), "la suppression logique ne doit jamais toucher le NAS"


# ================================ Scan / import ================================

async def test_scan_imports_subdirectories_and_is_idempotent(
    client, db_session, admin_user, tmp_path, monkeypatch
):
    root = mount_nas(tmp_path)
    write_nas(root, "IMG_0001.jpg", make_image_bytes(width=100, height=60))
    write_nas(root, "2026/été/vacances 2.jpg", make_image_bytes(width=80, height=80))
    write_nas(root, "ignore.txt", b"pas une photo")
    storage = configure_storage(monkeypatch, nas_path=root)

    result = await scan_import(db_session, admin_user.id)
    assert result["state"] == "available"
    assert result["files_seen"] == 2
    assert result["created"] == 2
    assert result["missing_marked"] == 0

    rows = await photo_rows(db_session)
    assert len(rows) == 2
    by_name = {row.original_filename: row for row in rows}
    assert "IMG_0001.jpg" in by_name
    assert "vacances 2.jpg" in by_name
    nested = by_name["vacances 2.jpg"]
    assert nested.storage_backend == "nas"
    assert nested.storage_path.startswith("2026/été/")
    assert nested.mime_type == "image/jpeg"
    assert nested.status == "pending"
    assert nested.taken_at is not None
    # Un job d'ingest par photo importée.
    jobs = list((await db_session.execute(select(PhotoJob))).scalars().all())
    assert {job.type for job in jobs} == {"ingest"}

    # Pipeline complet : miniatures locales, analyse en file.
    await drain_jobs(db_session)
    for row in await photo_rows(db_session):
        await db_session.refresh(row)
        assert row.status == "ready"

    # Idempotence : un second scan ne crée ni ne re-importe rien.
    second = await scan_import(db_session, admin_user.id)
    assert second["state"] == "available"
    assert second["created"] == 0
    assert second["updated_paths"] == 0
    assert second["missing_marked"] == 0
    assert len(await photo_rows(db_session)) == 2

    # Le hash n'est pas recalculé pour un fichier déjà référencé :
    # la photo conserve son content_hash d'origine.
    first_hash = (await photo_rows(db_session))[0].content_hash
    await scan_import(db_session, admin_user.id)
    assert (await photo_rows(db_session))[0].content_hash == first_hash
    assert storage.default_backend_name == "nas"


async def test_scan_handles_batches_beyond_one_batch(db_session, admin_user, tmp_path, monkeypatch):
    from app.services.photo import scan as scan_mod

    root = mount_nas(tmp_path)
    total = scan_mod.BATCH_SIZE + 7  # force plusieurs lots SQL
    for index in range(total):
        # Contenus tous différents (couleur unique) : pas de dédup.
        write_nas(
            root,
            f"batch_{index:04d}.jpg",
            make_image_bytes(color=(index % 255, (index * 7) % 255, (index * 13) % 255)),
        )
    configure_storage(monkeypatch, nas_path=root)

    result = await scan_import(db_session, admin_user.id)
    assert result["created"] == total
    assert len(await photo_rows(db_session)) == total


async def test_scan_dedup_by_hash_and_move_detection(db_session, admin_user, tmp_path, monkeypatch):
    root = mount_nas(tmp_path)
    data = make_image_bytes(width=90, height=70)
    original = write_nas(root, "album/photo.jpg", data)
    configure_storage(monkeypatch, nas_path=root)

    result = await scan_import(db_session, admin_user.id)
    assert result["created"] == 1
    row = (await photo_rows(db_session))[0]
    assert row.storage_path == "album/photo.jpg"
    original_hash = row.content_hash

    # Copie (l'ancien fichier existe toujours) → pas d'import.
    copy = write_nas(root, "album/photo - copie.jpg", data)
    result = await scan_import(db_session, admin_user.id)
    assert result["created"] == 0
    assert result["updated_paths"] == 0
    assert len(await photo_rows(db_session)) == 1

    # Déplacement / renommage → storage_path mis à jour, pas de doublon.
    # (La copie est retirée : avec deux exemplaires du même contenu non
    # référencés, l'un quelconque serait un candidat valable.)
    copy.unlink()
    original.rename(root / "album/photo renommée.jpg")
    result = await scan_import(db_session, admin_user.id)
    assert result["created"] == 0
    assert result["updated_paths"] == 1
    rows = await photo_rows(db_session)
    assert len(rows) == 1
    assert rows[0].storage_path == "album/photo renommée.jpg"
    assert rows[0].content_hash == original_hash
    assert (root / rows[0].storage_path).is_file()


async def test_scan_ignores_symlinks(db_session, admin_user, tmp_path, monkeypatch):
    root = mount_nas(tmp_path)
    outside = tmp_path / "outside-secret.jpg"
    outside.write_bytes(make_image_bytes())
    write_nas(root, "real.jpg", make_image_bytes())
    (root / "linked.jpg").symlink_to(outside)
    configure_storage(monkeypatch, nas_path=root)

    result = await scan_import(db_session, admin_user.id)
    assert result["created"] == 1
    rows = await photo_rows(db_session)
    assert [row.original_filename for row in rows] == ["real.jpg"]


async def test_scan_unavailable_aborts_without_any_deletion(
    client, db_session, admin_user, admin_headers, tmp_path, monkeypatch
):
    """Monture absente → scan interrompu, AUCUNE suppression, aucune photo
    marquée manquante."""
    root = mount_nas(tmp_path)
    configure_storage(monkeypatch, nas_path=root)
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    row = await db_session.get(Photo, photo_id)
    original = root / row.storage_path
    assert original.is_file()

    # « Démonter » : le répertoire pointé n'existe plus.
    shutil.rmtree(root)

    result = await scan_import(db_session, admin_user.id)
    assert result["state"] == "unavailable"
    assert result["created"] == 0
    assert result["missing_marked"] == 0

    await db_session.refresh(row)
    assert row.is_deleted is False, "un NAS indisponible ne doit rien marquer"
    # Et aucun fichier n'a été supprimé (le dossier est simplement parti).
    last = await db_session.execute(select(PhotoScanRun).order_by(PhotoScanRun.id.desc()))
    run = last.scalars().first()
    assert run.state == "unavailable"


async def test_scan_marks_missing_only_when_available(
    client, db_session, admin_user, admin_headers, tmp_path, monkeypatch
):
    root = mount_nas(tmp_path)
    configure_storage(monkeypatch, nas_path=root)
    keep = await upload_photo(client, admin_headers, make_image_bytes(width=60, height=60))
    gone = await upload_photo(client, admin_headers, make_image_bytes(width=70, height=70))
    keep_row = await db_session.get(Photo, keep.json()["items"][0]["id"])
    gone_row = await db_session.get(Photo, gone.json()["items"][0]["id"])

    # Suppression directe sur le disque (simulation « fichier parti »).
    (root / gone_row.storage_path).unlink()
    assert not (root / gone_row.storage_path).exists()

    result = await scan_import(db_session, admin_user.id)
    assert result["state"] == "available"
    assert result["missing_marked"] == 1

    await db_session.refresh(gone_row)
    await db_session.refresh(keep_row)
    assert gone_row.is_deleted is True
    assert gone_row.deleted_at is not None
    assert keep_row.is_deleted is False
    # Aucun fichier supprimé par le scan (le fichier survivant est intact).
    assert (root / keep_row.storage_path).is_file()


async def test_scan_does_not_touch_other_backend_photos(
    client, db_session, admin_user, admin_headers, tmp_path, monkeypatch
):
    """Isolation A/B : une photo locale n'est ni dupliquée ni marquée
    manquante par un scan NAS."""
    # Photo locale (backend courant local).
    configure_storage(monkeypatch, backend="local")
    same_bytes = make_image_bytes(width=50, height=50)
    local_resp = await upload_photo(client, admin_headers, same_bytes)
    local_id = local_resp.json()["items"][0]["id"]
    local_row = await db_session.get(Photo, local_id)
    assert local_row.storage_backend == "local"

    # Même contenu côté NAS : le dédup est propre à chaque backend.
    root = mount_nas(tmp_path)
    write_nas(root, "mirror.jpg", same_bytes)
    configure_storage(monkeypatch, nas_path=root)

    result = await scan_import(db_session, admin_user.id)
    assert result["state"] == "available"
    rows = await photo_rows(db_session)
    backends = sorted(row.storage_backend for row in rows)
    # Le contenu est dupliqué entre backends, jamais fusionné.
    assert backends == ["local", "nas"]
    assert result["missing_marked"] == 0

    await db_session.refresh(local_row)
    assert local_row.is_deleted is False


async def test_scan_references_videos_without_analysis(db_session, admin_user, tmp_path, monkeypatch):
    root = mount_nas(tmp_path)
    write_nas(root, "videos/clip.mp4", b"\x00\x00\x00\x18ftypisom-video")
    write_nas(root, "videos/move.mov", b"\x00\x00\x00\x14ftypqt  -video")
    configure_storage(monkeypatch, nas_path=root)

    result = await scan_import(db_session, admin_user.id)
    assert result["created"] == 2

    rows = await photo_rows(db_session)
    by_name = {row.original_filename: row for row in rows}
    assert by_name["clip.mp4"].mime_type == "video/mp4"
    assert by_name["move.mov"].mime_type == "video/quicktime"

    # Ingest : référencées (status ready) mais sans analyse image.
    await drain_jobs(db_session)
    for row in rows:
        await db_session.refresh(row)
        assert row.status == "ready"
        assert row.analysis_status == "skipped"
    # Aucun job d'analyse / embedding ne part sur une vidéo.
    jobs = list((await db_session.execute(select(PhotoJob))).scalars().all())
    assert all(job.type == "ingest" for job in jobs)


async def test_scan_references_heic_when_pillow_cannot_decode(
    db_session, admin_user, tmp_path, monkeypatch
):
    """Limitation documentée : sans pillow-heif, l'HEIC est référencé
    (original intact, status ready) mais ni miniatures ni analyse."""
    import importlib.util

    if importlib.util.find_spec("pillow_heif") is not None:
        pytest.skip("pillow-heif installé : le décodage HEIC fonctionne ici")

    root = mount_nas(tmp_path)
    write_nas(root, "iphone/IMG_9999.heic", b"\x00\x00\x00\x18ftypheic-not-a-real-image")
    configure_storage(monkeypatch, nas_path=root)

    result = await scan_import(db_session, admin_user.id)
    assert result["created"] == 1
    row = (await photo_rows(db_session))[0]
    assert row.mime_type == "image/heic"
    assert row.storage_path == "iphone/IMG_9999.heic"

    await drain_jobs(db_session)
    await db_session.refresh(row)
    # Référencée sans faire échouer la file (3 retries → failed).
    assert row.status == "ready"
    assert row.analysis_status == "skipped"
    assert row.error and "HEIC" in row.error


async def test_scan_interrupted_run_then_resume(
    db_session, admin_user, tmp_path, monkeypatch
):
    from app.services.photo import scan as scan_mod

    root = mount_nas(tmp_path)
    write_nas(root, "one.jpg", make_image_bytes())
    write_nas(root, "two.jpg", make_image_bytes())
    configure_storage(monkeypatch, nas_path=root)

    async def broken_mark(*args, **kwargs):
        raise RuntimeError("panne en cours de scan")

    original_mark = scan_mod._mark_missing
    scan_mod._mark_missing = broken_mark
    try:
        with pytest.raises(Exception):
            await scan_import(db_session, admin_user.id)
    finally:
        scan_mod._mark_missing = original_mark

    runs = list((await db_session.execute(select(PhotoScanRun))).scalars().all())
    assert runs[-1].state == "error"
    assert runs[-1].finished_at is not None

    # Reprise : le nouveau scan termine proprement.
    result = await scan_import(db_session, admin_user.id)
    assert result["state"] == "available"
    assert result["created"] == 0  # les fichiers étaient déjà importés


# ================================ API ================================

async def test_storage_status_endpoint(client, db_session, admin_user, admin_headers, tmp_path, monkeypatch):
    root = mount_nas(tmp_path)
    configure_storage(monkeypatch, nas_path=root)

    response = await client.get("/photos/storage/status", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["backend"] == "nas"
    assert body["path"] == str(root)
    assert body["state"] == "available"
    assert "nas" in body["backends"]
    assert body["last_scan"] is None

    await scan_import(db_session, admin_user.id)
    response = await client.get("/photos/storage/status", headers=admin_headers)
    body = response.json()
    assert body["last_scan"] is not None
    assert body["last_scan"]["state"] == "available"
    assert body["last_scan"]["created"] == 0  # aucun fichier dans le NAS pour ce scan
    assert body["last_scan"]["files_seen"] == 0


async def test_scan_endpoint_queues_job_and_scans(
    client, db_session, admin_headers, tmp_path, monkeypatch
):
    root = mount_nas(tmp_path)
    write_nas(root, "api.jpg", make_image_bytes())
    configure_storage(monkeypatch, nas_path=root)

    response = await client.post("/photos/import/scan", headers=admin_headers)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["queued"] is True
    assert body["job_id"]

    # Un second appel ne double pas le scan en file.
    again = await client.post("/photos/import/scan", headers=admin_headers)
    assert again.status_code == 202
    assert again.json()["queued"] is False

    await drain_jobs(db_session)
    jobs = list((await db_session.execute(select(PhotoJob))).scalars().all())
    scan_jobs = [job for job in jobs if job.type == "scan_import"]
    assert len(scan_jobs) == 1
    assert scan_jobs[0].status == "done"

    rows = await photo_rows(db_session)
    assert [row.original_filename for row in rows] == ["api.jpg"]

    status = await client.get("/photos/storage/status", headers=admin_headers)
    assert status.json()["last_scan"]["created"] == 1


async def test_scan_endpoint_rejects_unavailable_storage(
    client, admin_headers, tmp_path, monkeypatch
):
    configure_storage(monkeypatch, nas_path=tmp_path / "never-mounted")
    response = await client.post("/photos/import/scan", headers=admin_headers)
    assert response.status_code == 409
    assert "indisponible" in response.json()["detail"]


async def test_storage_endpoints_require_permissions(
    client, db_session, tmp_path, monkeypatch
):
    root = mount_nas(tmp_path)
    configure_storage(monkeypatch, nas_path=root)
    limited = await create_limited_user(
        db_session, "storview", "password123", ["photos.view"]
    )
    headers = await login(client, "storview", "password123")

    status = await client.get("/photos/storage/status", headers=headers)
    assert status.status_code == 200
    # Pas la permission d'importer : scan refusé.
    scan = await client.post("/photos/import/scan", headers=headers)
    assert scan.status_code == 403
    assert limited is not None


# ================================ Scan périodique ================================

async def test_maybe_schedule_scan_disabled_or_without_prior_run(
    db_session, admin_user, tmp_path, monkeypatch
):
    root = mount_nas(tmp_path)
    configure_storage(monkeypatch, nas_path=root, scan_enabled=False)
    await maybe_schedule_scan(db_session)
    jobs = list((await db_session.execute(select(PhotoJob))).scalars().all())
    assert jobs == []

    # Activé mais aucun scan manuel antérieur : pas d'attribution de
    # propriétaire → rien n'est enfilé.
    configure_storage(monkeypatch, nas_path=root, scan_enabled=True)
    await maybe_schedule_scan(db_session)
    jobs = list((await db_session.execute(select(PhotoJob))).scalars().all())
    assert jobs == []


async def test_maybe_schedule_scan_respects_interval_and_dedups(
    db_session, admin_user, tmp_path, monkeypatch
):
    root = mount_nas(tmp_path)
    configure_storage(
        monkeypatch, nas_path=root, scan_enabled=True, scan_interval=300
    )

    # Dernier scan récent → pas de nouveau scan.
    # started_at est un défaut serveur (UTC naive) : le test reproduit
    # exactement ce que la base produit, pas l'heure locale Python.
    utc_now = datetime.now(UTC).replace(tzinfo=None)
    recent = PhotoScanRun(
        owner_id=admin_user.id, backend="nas", state="available",
        started_at=utc_now, finished_at=utc_now,
    )
    db_session.add(recent)
    await db_session.commit()
    await maybe_schedule_scan(db_session)
    assert list((await db_session.execute(select(PhotoJob))).scalars().all()) == []

    # Dernier scan ancien → scan mis en file.
    recent.started_at = utc_now - timedelta(minutes=10)
    await db_session.commit()
    await maybe_schedule_scan(db_session)
    jobs = list((await db_session.execute(select(PhotoJob))).scalars().all())
    assert [job.type for job in jobs] == ["scan_import"]
    assert jobs[0].payload_json["owner_id"] == admin_user.id
    assert jobs[0].payload_json["backend"] == "nas"

    # Un job déjà en file → pas de doublon.
    await maybe_schedule_scan(db_session)
    jobs = list((await db_session.execute(select(PhotoJob))).scalars().all())
    assert len(jobs) == 1

    # Le scan auto tourne réellement via la file.
    await drain_jobs(db_session)
    done = list((await db_session.execute(select(PhotoJob))).scalars().all())
    assert all(job.status == "done" for job in done)


# ================================ Lecture indépendante de la config ================================

async def test_existing_photo_readable_after_backend_config_change(
    client, db_session, admin_user, admin_headers, tmp_path, monkeypatch
):
    """Changer le backend courant ne doit pas rendre une photo existante
    inaccessible : la lecture suit la colonne de la photo."""
    root = mount_nas(tmp_path)
    configure_storage(monkeypatch, nas_path=root)
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    row = await db_session.get(Photo, photo_id)
    assert row.storage_backend == "nas"

    # Le backend courant repasse en local (les futurs uploads iraient en
    # local) mais le NAS reste configuré : la photo reste servable.
    configure_storage(monkeypatch, backend="local", nas_path=root)
    file_response = await client.get(
        f"/photos/{photo_id}/file?size=original", headers=admin_headers
    )
    assert file_response.status_code == 200
    assert file_response.content == (root / row.storage_path).read_bytes()

    # NAS retiré complètement de la configuration : erreur propre (404),
    # jamais un 500.
    configure_storage(monkeypatch, backend="local", nas_path="")
    gone = await client.get(
        f"/photos/{photo_id}/file?size=original", headers=admin_headers
    )
    assert gone.status_code == 404
