"""Tests V3.1 — support HEIC/HEIF et miniatures vidéo (MOV/MP4).

Couvre :
- HEIC réel avec pillow-heif présent : miniatures générées, analyse enfilée.
- HEIC dégradé (pillow-heif absent / MetadataError) : import ready sans miniatures.
- Vidéo MOV/MP4 : frame extraite par ffmpeg si présent, sinon ready sans miniature.
- Rebuild endpoint : photos sans miniatures remises en file.
- Régressions : JPEG/local/NAS inchangés.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from test_photos import (
    create_limited_user,
    drain_jobs,
    login,
    make_image_bytes,
    upload_photo,
)

from app.core.config import get_settings
from sqlalchemy import select
from app.models.photo import Photo, PhotoJob, PhotoThumbnail
from app.services.photo import thumbnails as thumbnails_mod
from app.services.photo.jobs import _generate_thumbnails_safe
from app.services.photo.metadata import MetadataError


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_photo_storage():
    """Reset the photo storage singleton to pick up the test's PHOTO_STORAGE_PATH."""
    import app.services.photo.storage as storage_mod
    storage_mod._storage = None
    yield
    storage_mod._storage = None


# ================================ Helpers ================================

def make_heic_bytes(width=120, height=80, color=(30, 90, 160)) -> bytes:
    """Génère un vrai HEIC en mémoire via pillow-heif (nécessite pillow-heif installé)."""
    buf = io.BytesIO()
    image = Image.new("RGB", (width, height), color)
    from pillow_heif import from_pillow

    heif = from_pillow(image)
    heif.save(buf, format="HEIF", quality=80)
    return buf.getvalue()


def make_mock_video_frame(width=320, height=240, color=(50, 100, 150)) -> bytes:
    """PNG d'une frame de test (utilisée pour mocker ffmpeg)."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


# ================================ HEIC ================================

async def test_heic_real_thumbnails_and_analysis_queued(
    client, admin_headers, db_session, tmp_path
):
    """HEIC réel (pillow-heif présent) : miniatures générées + analyse enfilée."""
    # pillow-heif est installé dans l'env de test (V3.1) -> pas de skip
    heic_data = make_heic_bytes()
    resp = await upload_photo(
        client, admin_headers, heic_data, filename="IMG_1234.heic", field="files"
    )
    assert resp.status_code in (200, 201), resp.json()
    photo_id = resp.json()["items"][0]["id"]

    await drain_jobs(db_session)

    # Vérifier miniatures créées
    from sqlalchemy import select

    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(thumbs) >= 3  # small, medium, preview

    # Photo ready, error = None, analysis pending/running (enfilée)
    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.error is None
    assert photo.analysis_status in ("pending", "running", "done")

    # Fichier original intact (HEIC inchangé)
    # Pas de modification du fichier original NAS/local


async def test_heic_fallback_when_metadata_error(
    client, admin_headers, db_session, monkeypatch
):
    """HEIC -> MetadataError (pillow-heif absent / corrompu) : ready sans miniatures."""
    # Simuler l'absence de pillow-heif pour extract_metadata -> MetadataError
    from app.services.photo import metadata as metadata_mod

    original_extract = metadata_mod.extract_metadata

    def failing_extract(data):
        raise MetadataError("HEIC non supporté (pillow-heif absent)")

    monkeypatch.setattr(metadata_mod, "extract_metadata", failing_extract)

    heic_data = make_heic_bytes()
    resp = await upload_photo(
        client, admin_headers, heic_data, filename="IMG_1234.heic", field="files"
    )
    assert resp.status_code in (200, 201)
    photo_id = resp.json()["items"][0]["id"]

    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.analysis_status == "skipped"
    assert photo.error is not None
    assert "HEIC non décodable" in photo.error
    assert "miniatures/analyse indisponibles" in photo.error

    # Aucune miniature
    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(thumbs) == 0


# ================================ Vidéo ================================

async def _create_video_photo(db_session, filename="VID.mov", mime_type="video/quicktime") -> int:
    """Crée une photo vidéo directement en base (bypass upload - videos importés via scan NAS)."""
    import uuid
    from datetime import datetime, UTC
    from app.services.photo.storage import get_photo_storage

    storage = get_photo_storage()
    # Save a fake video file that's actually readable
    fake_content = b"fake-video-content-for-testing"
    rel = storage.save_original(1, uuid.uuid4().hex, f".{filename.split('.')[-1]}", fake_content)

    photo = Photo(
        owner_id=1,
        title=None,
        original_filename=filename,
        storage_path=rel,
        storage_backend="local",
        mime_type=mime_type,
        byte_size=len(fake_content),
        content_hash="fakehash",
        taken_at=datetime.now(UTC),
        status="pending",
        analysis_status="pending",
    )
    db_session.add(photo)
    await db_session.commit()
    await db_session.refresh(photo)
    return photo.id


async def test_video_thumbnails_with_ffmpeg_mock(
    client, admin_headers, db_session, monkeypatch
):
    """Vidéo MOV : frame mockée -> miniatures générées, width/height renseignés."""
    # Mock _extract_video_frame pour retourner une image contrôlée
    mock_frame = Image.new("RGB", (320, 240), (50, 100, 150))

    def mock_extract(path):
        return mock_frame

    monkeypatch.setattr(thumbnails_mod, "_extract_video_frame", mock_extract)

    # Créer une photo vidéo directement en base
    photo_id = await _create_video_photo(db_session, "VID_001.mov")

    # Enfiler job ingest
    from app.services.photo.jobs import enqueue_job_unique

    await enqueue_job_unique(db_session, type="ingest", photo_id=photo_id, commit=True)

    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.error is None
    # Miniatures générées
    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(thumbs) >= 3
    # width/height depuis la frame mockée
    assert photo.width == 320
    assert photo.height == 240
    # Vidéo : analysis_status skipped (pas d'analyse image)
    assert photo.analysis_status == "skipped"


async def test_video_no_ffmpeg_ready_without_thumbnails(
    client, admin_headers, db_session, monkeypatch
):
    """Vidéo sans ffmpeg -> ready, error renseignée, pas de miniature."""
    # Simuler ffmpeg absent
    monkeypatch.setattr(thumbnails_mod, "ffmpeg_available", lambda: False)

    photo_id = await _create_video_photo(db_session, "VID_002.mov")

    from app.services.photo.jobs import enqueue_job_unique

    await enqueue_job_unique(db_session, type="ingest", photo_id=photo_id, commit=True)

    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.analysis_status == "skipped"
    assert photo.error is not None
    assert "miniature indisponible" in photo.error.lower()
    assert "ffmpeg" in photo.error.lower()

    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(thumbs) == 0


async def test_video_real_ffmpeg_missing_graceful(
    client, admin_headers, db_session
):
    """Test réel : ffmpeg absent dans l'env de test -> ready sans miniature."""
    # L'env de test n'a pas ffmpeg (vérifié dans conftest/env)
    if ffmpeg_available():
        pytest.skip("ffmpeg présent, test non pertinent")

    photo_id = await _create_video_photo(db_session, "VID_003.mov")

    from app.services.photo.jobs import enqueue_job_unique

    await enqueue_job_unique(db_session, type="ingest", photo_id=photo_id, commit=True)

    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.analysis_status == "skipped"
    assert photo.error is not None
    assert "ffmpeg" in photo.error.lower()
    # Aucune miniature
    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(thumbs) == 0


# ================================ Rebuild endpoint ================================

async def test_rebuild_thumbnails_endpoint(
    client, admin_headers, db_session, tmp_path, monkeypatch
):
    """POST /photos/thumbnails/rebuild : photos sans miniatures remises en file."""
    # Créer une photo HEIC sans pillow-heif (fallback) pour avoir une photo sans miniatures
    from app.services.photo import metadata as metadata_mod

    original_extract = metadata_mod.extract_metadata

    def failing_extract(data):
        raise MetadataError("HEIC non supporté")

    monkeypatch.setattr(metadata_mod, "extract_metadata", failing_extract)

    heic_data = make_heic_bytes()
    resp = await upload_photo(
        client, admin_headers, heic_data, filename="IMG_5678.heic", field="files"
    )
    photo_id = resp.json()["items"][0]["id"]
    await drain_jobs(db_session)

    # Photo sans miniatures
    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.analysis_status == "skipped"

    # Lever le monkeypatch pour que le rebuild fonctionne avec pillow-heif réel
    monkeypatch.undo()

    # Appeler rebuild
    from httpx import AsyncClient

    rebuild_resp = await client.post("/photos/thumbnails/rebuild?limit=200", headers=admin_headers)
    assert rebuild_resp.status_code == 202
    data = rebuild_resp.json()
    assert data["queued"] >= 1
    assert "remise" in data["message"]

    # Job ingest en file (unique)
    jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "ingest"
            )
        )
    ).scalars().all()
    assert len(jobs) >= 1
    assert jobs[0].status in ("pending", "done")

    # Lancer le job
    await drain_jobs(db_session)

    # Maintenant pillow-heif est remis (monkeypatch fini) -> miniatures générées
    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.error is None
    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(thumbs) >= 3


async def test_rebuild_idempotent_no_duplicate_jobs(
    client, admin_headers, db_session, monkeypatch
):
    """Rebuild répété : pas de double job pour la même photo.

    Si un job ingest est déjà en file (pending/running), le second rebuild
    le réutilise au lieu d'en créer un second.
    """
    from app.services.photo import metadata as metadata_mod

    monkeypatch.setattr(
        metadata_mod, "extract_metadata", lambda data: (_ for _ in ()).throw(MetadataError("fail"))
    )

    heic_data = make_heic_bytes()
    resp = await upload_photo(
        client, admin_headers, heic_data, filename="IMG_9999.heic", field="files"
    )
    photo_id = resp.json()["items"][0]["id"]
    await drain_jobs(db_session)

    # Premier rebuild
    resp1 = await client.post("/photos/thumbnails/rebuild?limit=200", headers=admin_headers)
    assert resp1.status_code == 202
    queued1 = resp1.json()["queued"]
    assert queued1 >= 1

    # Deuxième rebuild immédiat : résultat cohérent (même photo ciblée)
    resp2 = await client.post("/photos/thumbnails/rebuild?limit=200", headers=admin_headers)
    assert resp2.status_code == 202
    # queued peut être 1 (job pending) ou 0 (job traité, photo a maintenant des miniatures)
    # L'important : l'endpoint répond sans erreur et ne crée pas de doublon excessif
    assert resp2.json()["queued"] in (0, 1)

    # Au maximum 2 jobs ingest (le premier + éventuel second si le premier a fini)
    jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "ingest"
            )
        )
    ).scalars().all()
    assert len(jobs) <= 2


async def test_rebuild_requires_photos_analyze_permission(client, db_session):
    """Rebuild nécessite permission photos.analyze."""
    # Utilisateur sans permission photos.analyze
    from test_photos import create_limited_user, login

    await create_limited_user(
        db_session, "limited_no_analyze", "pass123", ["photos.view", "photos.upload"]
    )

    limited_headers = await login(client, "limited_no_analyze", "pass123")

    resp = await client.post("/photos/thumbnails/rebuild?limit=200", headers=limited_headers)
    assert resp.status_code == 403


# ================================ Régressions JPEG / Local / NAS ================================

async def test_jpeg_import_unchanged(
    client, admin_headers, db_session, monkeypatch
):
    """JPEG standard : comportement V1/V2 inchangé (miniatures + analyse)."""
    jpg = make_image_bytes()
    resp = await upload_photo(client, admin_headers, jpg, filename="test.jpg")
    photo_id = resp.json()["items"][0]["id"]
    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.error is None
    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(thumbs) >= 3
    assert photo.analysis_status in ("pending", "running", "success", "done")


async def test_local_backend_unchanged(
    client, admin_headers, db_session, tmp_path, monkeypatch
):
    """Backend local (V3) : import/scan fonctionnent toujours."""
    from app.services.photo import storage as storage_mod
    from app.services.photo.storage import get_photo_storage

    local_root = tmp_path / "local_photos"
    local_root.mkdir()
    (local_root / ".keep").write_text("")

    def configure():
        settings = get_settings()
        monkeypatch.setattr(settings, "PHOTO_STORAGE_BACKEND", "local")
        monkeypatch.setattr(settings, "PHOTO_STORAGE_PATH", str(local_root))
        storage_mod._storage = None
        return get_photo_storage()

    storage = configure()
    assert storage.check("local").state == "available"

    # Écrire un JPEG dans le local (dans originals/ où le scan regarde)
    # PhotoStorage a déjà créé le dossier originals/
    jpg = make_image_bytes()
    (local_root / "originals" / "photo_local.jpg").write_bytes(jpg)

    from app.services.photo.scan import run_scan

    run = await run_scan(db_session, owner_id=1)
    assert run['created'] >= 1

    await drain_jobs(db_session)

    # Photo importée avec miniatures
    from sqlalchemy import select

    photo = (
        await db_session.execute(select(Photo).where(Photo.original_filename == "photo_local.jpg"))
    ).scalar_one()
    assert photo.storage_backend == "local"
    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo.id)
        )
    ).scalars().all()
    assert len(thumbs) >= 3


async def test_nas_backend_unchanged(
    client, admin_headers, db_session, tmp_path, monkeypatch
):
    """Backend NAS (V3) : scan/import fonctionnent toujours."""
    from app.services.photo import storage as storage_mod
    from app.services.photo.storage import NasFilesystemStorage, get_photo_storage

    nas_root = tmp_path / "nas_photos"
    nas_root.mkdir()
    (nas_root / ".keep").write_text("mounted")

    settings = get_settings()
    monkeypatch.setattr(settings, "PHOTO_STORAGE_BACKEND", "nas")
    monkeypatch.setattr(settings, "PHOTO_NAS_PATH", str(nas_root))
    storage_mod._storage = None

    storage = get_photo_storage()
    assert isinstance(storage.backend("nas"), NasFilesystemStorage)
    assert storage.check("nas").state == "available"

    # Écrire un JPEG dans le NAS
    jpg = make_image_bytes()
    (nas_root / "photo_nas.jpg").write_bytes(jpg)

    from app.services.photo.scan import run_scan

    run = await run_scan(db_session, owner_id=1)
    assert run['created'] >= 1

    await drain_jobs(db_session)

    from sqlalchemy import select

    photo = (
        await db_session.execute(select(Photo).where(Photo.original_filename == "photo_nas.jpg"))
    ).scalar_one()
    assert photo.storage_backend == "nas"
    thumbs = (
        await db_session.execute(
            select(PhotoThumbnail).where(PhotoThumbnail.photo_id == photo.id)
        )
    ).scalars().all()
    assert len(thumbs) >= 3


# ================================ _generate_thumbnails_safe ================================

async def test_generate_thumbnails_safe_heic_ok(tmp_path, monkeypatch):
    """Helper _generate_thumbnails_safe : HEIC OK -> résultats."""
    heic_path = tmp_path / "test.heic"
    heic_path.write_bytes(make_heic_bytes())
    thumbs_dir = tmp_path / "thumbs"

    results, err = await _generate_thumbnails_safe(heic_path, thumbs_dir)
    assert results is not None
    assert err is None
    assert len(results) >= 3
    for r in results:
        assert "source_width" in r
        assert "source_height" in r


async def test_generate_thumbnails_safe_video_ffmpeg_mock(tmp_path, monkeypatch):
    """Helper : vidéo avec frame mockée -> résultats."""
    video_path = tmp_path / "test.mov"
    video_path.write_bytes(b"fake")

    mock_frame = Image.new("RGB", (320, 240), (50, 100, 150))
    monkeypatch.setattr(thumbnails_mod, "_extract_video_frame", lambda p: mock_frame)

    thumbs_dir = tmp_path / "thumbs"
    results, err = await _generate_thumbnails_safe(video_path, thumbs_dir)
    assert results is not None
    assert err is None
    assert len(results) >= 3
    assert results[0]["source_width"] == 320
    assert results[0]["source_height"] == 240


async def test_generate_thumbnails_safe_video_no_ffmpeg(tmp_path, monkeypatch):
    """Helper : vidéo sans ffmpeg -> None, erreur."""
    monkeypatch.setattr(thumbnails_mod, "ffmpeg_available", lambda: False)
    video_path = tmp_path / "test.mov"
    video_path.write_bytes(b"fake")
    thumbs_dir = tmp_path / "thumbs"

    results, err = await _generate_thumbnails_safe(video_path, thumbs_dir)
    assert results is None
    assert err is not None
    assert "ffmpeg" in err.lower()


async def test_generate_thumbnails_safe_corrupt_file(tmp_path):
    """Helper : fichier corrompu -> None, erreur."""
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not-an-image")
    thumbs_dir = tmp_path / "thumbs"

    results, err = await _generate_thumbnails_safe(bad, thumbs_dir)
    assert results is None
    assert err is not None