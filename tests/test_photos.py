"""Tests du module Photos.

Couvre : import/storage, miniatures, métadonnées EXIF, permissions,
isolation entre utilisateurs, albums, tags, personnes, lieux, recherche
naturelle, jobs d'arrière-plan, retouche, suppression logique, doublons
et les régressions de l'audit technique.
"""

import hashlib
import io
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy import select, update as sa_update

from app.models.photo import Photo, PhotoFace, PhotoJob, PhotoPlace
from app.models.user import UserRole
from app.services.auth import create_user
from app.services.photo.jobs import (
    STALE_RUNNING_AFTER,
    enqueue_job,
    process_photo_jobs,
)
from app.services.rbac import RBACService


# ================================ Helpers ================================

def make_image_bytes(width=120, height=80, color=(30, 90, 160), exif: Image.Exif | None = None) -> bytes:
    buf = io.BytesIO()
    image = Image.new("RGB", (width, height), color)
    kwargs = {"format": "JPEG"}
    if exif is not None:
        kwargs["exif"] = exif
    image.save(buf, **kwargs)
    return buf.getvalue()


def make_exif_photo(taken="2023:07:15 10:30:00", width=120, height=80) -> bytes:
    exif = Image.Exif()
    exif[0x9003] = taken
    exif[0x010F] = "Canon"
    exif[0x0110] = "EOS R5"
    return make_image_bytes(width=width, height=height, exif=exif)


async def upload_photo(client, headers, data: bytes, filename="photo.jpg", field="files"):
    return await client.post(
        "/photos/upload",
        files=[(field, (filename, data, "image/jpeg"))],
        headers=headers,
    )


async def drain_jobs(db, max_rounds=6):
    """Exécute la file des jobs photo jusqu'à stabilisation."""
    total = 0
    for _ in range(max_rounds):
        processed = await process_photo_jobs(db, limit=20)
        total += processed
        if not processed:
            break
    return total


async def create_limited_user(db, username: str, password: str, permissions: list[str]):
    """Utilisateur avec un rôle personnalisé (permissions explicites)."""
    user = await create_user(db, {
        "username": username,
        "email": f"{username}@example.com",
        "password": password,
        "is_active": True,
        "role": UserRole.USER,
        "source": "local",
    })
    rbac = RBACService(db)
    role = await rbac.create_role(
        f"role_{username}", f"Rôle {username}", description="Rôle de test photos"
    )
    for code in permissions:
        perm = await rbac.get_permission_by_code(code)
        assert perm is not None, f"permission {code} absente du seed"
        await rbac.assign_permission_to_role(role.id, perm.id)
    await rbac.assign_role_to_user(user.id, role.id)
    return user


async def login(client, username, password):
    response = await client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    return {"Authorization": f"Bearer {token}"}


# ================================ Import / stockage ================================

@pytest.mark.asyncio
async def test_upload_creates_photo_and_original(client, db_session, admin_headers):
    data = make_image_bytes()
    response = await upload_photo(client, admin_headers, data, filename="vacances.jpg")
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["items"]) == 1
    photo = body["items"][0]
    assert photo["status"] == "pending"
    assert photo["original_filename"] == "vacances.jpg"
    assert photo["byte_size"] == len(data)

    row = await db_session.get(Photo, photo["id"])
    assert row is not None

    from app.services.photo.storage import get_photo_storage

    original = get_photo_storage().original_path(row.storage_path)
    assert original.is_file()
    assert original.read_bytes() == data


@pytest.mark.asyncio
async def test_upload_rejects_non_image(client, admin_headers):
    response = await upload_photo(
        client, admin_headers, b"ceci n'est pas une image", filename="fake.jpg"
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client, admin_headers):
    from app.core.config import get_settings

    settings = get_settings()
    original_limit = settings.PHOTO_MAX_UPLOAD_SIZE
    settings.PHOTO_MAX_UPLOAD_SIZE = 64
    try:
        response = await upload_photo(client, admin_headers, make_image_bytes())
        assert response.status_code == 400
    finally:
        settings.PHOTO_MAX_UPLOAD_SIZE = original_limit


@pytest.mark.asyncio
async def test_upload_requires_authentication(client):
    response = await upload_photo(client, {}, make_image_bytes())
    assert response.status_code in (401, 403)


# ================================ Pipeline ingest ================================

@pytest.mark.asyncio
async def test_ingest_pipeline_metadata_and_thumbnails(client, db_session, admin_headers):
    response = await upload_photo(
        client, admin_headers, make_exif_photo(), filename="exif.jpg"
    )
    photo_id = response.json()["items"][0]["id"]

    processed = await drain_jobs(db_session)
    assert processed >= 1

    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready", photo.error
    assert photo.width == 120 and photo.height == 80
    assert photo.taken_at == datetime(2023, 7, 15, 10, 30)
    assert photo.camera_make == "Canon"
    assert photo.camera_model == "EOS R5"

    detail = await client.get(f"/photos/{photo_id}", headers=admin_headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["status"] == "ready"
    assert payload["exif_json"]["make"] == "Canon"

    # Miniatures multi-tailles servies authentifiées.
    for size in ("tiny", "small", "medium", "large", "preview"):
        thumb = await client.get(
            f"/photos/{photo_id}/file", params={"size": size}, headers=admin_headers
        )
        assert thumb.status_code == 200, (size, thumb.text)
        assert thumb.headers["content-type"] == "image/jpeg"

    # Original téléchargeable.
    original = await client.get(
        f"/photos/{photo_id}/file",
        params={"size": "original", "download": "true"},
        headers=admin_headers,
    )
    assert original.status_code == 200
    assert "attachment" in original.headers["content-disposition"]


@pytest.mark.asyncio
async def test_ingest_uses_exif_orientation_for_display_size(client, db_session, admin_headers):
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: dimensions affichées permutées
    response = await upload_photo(
        client, admin_headers, make_image_bytes(width=100, height=200, exif=exif)
    )
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)
    photo = await db_session.get(Photo, photo_id)
    assert (photo.width, photo.height) == (200, 100)


@pytest.mark.asyncio
async def test_ingest_detects_gps_and_creates_place(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    photo.gps_latitude = 45.5
    photo.gps_longitude = 6.5
    await db_session.commit()

    from app.services.photo.jobs import enqueue_job

    await enqueue_job(db_session, type="ingest", photo_id=photo_id)
    await drain_jobs(db_session)

    await db_session.refresh(photo)
    assert photo.place_id is not None
    place = await db_session.get(PhotoPlace, photo.place_id)
    assert place.lat_cell == 45.5
    assert place.lon_cell == 6.5

    places = await client.get("/photos/places", headers=admin_headers)
    assert places.status_code == 200
    assert places.json()["total"] == 1
    assert places.json()["items"][0]["id"] == place.id
    assert places.json()["items"][0]["photo_count"] == 1


# ================================ Galerie / pagination ================================

@pytest.mark.asyncio
async def test_list_pagination_and_cursor(client, db_session, admin_headers):
    for day in (10, 11, 12):
        data = make_exif_photo(taken=f"2024:05:{day:02d} 12:00:00")
        await upload_photo(client, admin_headers, data, filename=f"p{day}.jpg")
    await drain_jobs(db_session)

    first = await client.get("/photos", params={"page_size": 2}, headers=admin_headers)
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    assert body["items"][0]["taken_at"] > body["items"][1]["taken_at"]

    second = await client.get(
        "/photos",
        params={"page_size": 2, "cursor": body["next_cursor"]},
        headers=admin_headers,
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_favorite_filter_and_patch(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    patched = await client.patch(
        f"/photos/{photo_id}",
        json={"is_favorite": True, "title": "Ma photo"},
        headers=admin_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["is_favorite"] is True
    assert patched.json()["title"] == "Ma photo"

    favorites = await client.get(
        "/photos", params={"favorite": True}, headers=admin_headers
    )
    assert favorites.json()["total"] == 1

    search = await client.get(
        "/photos", params={"search": "Ma photo"}, headers=admin_headers
    )
    assert search.json()["total"] == 1


@pytest.mark.asyncio
async def test_soft_delete_and_restore(client, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    deleted = await client.delete(f"/photos/{photo_id}", headers=admin_headers)
    assert deleted.status_code == 204

    detail = await client.get(f"/photos/{photo_id}", headers=admin_headers)
    assert detail.status_code == 404

    listing = await client.get("/photos", headers=admin_headers)
    assert listing.json()["total"] == 0

    restored = await client.post(f"/photos/{photo_id}/restore", headers=admin_headers)
    assert restored.status_code == 200
    assert restored.json()["is_deleted"] is False

    listing = await client.get("/photos", headers=admin_headers)
    assert listing.json()["total"] == 1


# ================================ Permissions / isolation ================================

@pytest.mark.asyncio
async def test_requires_photos_permission(client, auth_headers):
    listing = await client.get("/photos", headers=auth_headers)
    assert listing.status_code == 403

    upload = await upload_photo(client, auth_headers, make_image_bytes())
    assert upload.status_code == 403


@pytest.mark.asyncio
async def test_photos_private_between_users(client, db_session, admin_headers):
    # L'admin importe une photo.
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    # Un autre utilisateur, avec photos.view mais SANS photos.manage_all.
    await create_limited_user(db_session, "photo_viewer", "password123", ["photos.view"])
    other_headers = await login(client, "photo_viewer", "password123")

    detail = await client.get(f"/photos/{photo_id}", headers=other_headers)
    assert detail.status_code == 404

    listing = await client.get("/photos", headers=other_headers)
    assert listing.json()["total"] == 0

    file_resp = await client.get(
        f"/photos/{photo_id}/file", params={"size": "small"}, headers=other_headers
    )
    assert file_resp.status_code == 404

    # Sans authentification : refus. (Le client httpx conserve les cookies de
    # session des logins précédents : on les vide pour simuler un anonyme.)
    client.cookies.clear()
    anonymous = await client.get(f"/photos/{photo_id}/file", params={"size": "small"})
    assert anonymous.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_with_manage_all_can_read_other_photos(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    await create_limited_user(
        db_session, "photo_manager", "password123",
        ["photos.view", "photos.manage_all"],
    )
    manager_headers = await login(client, "photo_manager", "password123")

    detail = await client.get(f"/photos/{photo_id}", headers=manager_headers)
    assert detail.status_code == 200


# ================================ Albums ================================

@pytest.mark.asyncio
async def test_albums_flow(client, db_session, admin_headers):
    first = await upload_photo(client, admin_headers, make_image_bytes(color=(1, 2, 3)))
    second = await upload_photo(client, admin_headers, make_image_bytes(color=(4, 5, 6)))
    photo_ids = [first.json()["items"][0]["id"], second.json()["items"][0]["id"]]

    created = await client.post(
        "/photos/albums",
        json={"name": "Vacances 2024", "description": "Été"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    album_id = created.json()["id"]

    added = await client.post(
        f"/photos/albums/{album_id}/photos",
        json={"photo_ids": photo_ids},
        headers=admin_headers,
    )
    assert added.status_code == 200

    album = await client.get(f"/photos/albums/{album_id}", headers=admin_headers)
    assert album.json()["photo_count"] == 2

    in_album = await client.get(
        "/photos", params={"album_id": album_id}, headers=admin_headers
    )
    assert in_album.json()["total"] == 2

    listing = await client.get("/photos/albums", headers=admin_headers)
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["photo_count"] == 2

    removed = await client.delete(
        f"/photos/albums/{album_id}/photos/{photo_ids[0]}", headers=admin_headers
    )
    assert removed.status_code == 200

    deleted = await client.delete(f"/photos/albums/{album_id}", headers=admin_headers)
    assert deleted.status_code == 204

    listing = await client.get("/photos/albums", headers=admin_headers)
    assert listing.json()["total"] == 0


@pytest.mark.asyncio
async def test_album_duplicate_name_conflict(client, admin_headers):
    payload = {"name": "Doublon"}
    assert (await client.post("/photos/albums", json=payload, headers=admin_headers)).status_code == 201
    conflict = await client.post("/photos/albums", json=payload, headers=admin_headers)
    assert conflict.status_code == 409


# ================================ Tags / recherche ================================

@pytest.mark.asyncio
async def test_manual_tag_and_natural_search(client, db_session, admin_headers):
    response = await upload_photo(
        client, admin_headers, make_exif_photo(), filename="montagne.jpg"
    )
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    tagged = await client.post(
        f"/photos/{photo_id}/tags",
        json={"name": "Montagne"},
        headers=admin_headers,
    )
    assert tagged.status_code == 201
    assert tagged.json()["slug"] == "montagne"

    # Recherche naturelle : le nom de tag est reconnu comme entité.
    found = await client.get("/photos/search", params={"q": "photos de montagne"}, headers=admin_headers)
    assert found.status_code == 200
    assert found.json()["total"] == 1

    tags = await client.get("/photos/tags", headers=admin_headers)
    assert any(tag["slug"] == "montagne" for tag in tags.json()["items"])

    removed = await client.delete(
        f"/photos/{photo_id}/tags/{tagged.json()['id']}", headers=admin_headers
    )
    assert removed.status_code == 200

    found = await client.get("/photos/search", params={"q": "montagne"}, headers=admin_headers)
    assert found.json()["total"] == 0


@pytest.mark.asyncio
async def test_analysis_job_creates_metadata_tags(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    analysis = await client.get(f"/photos/{photo_id}/analysis", headers=admin_headers)
    assert analysis.status_code == 200
    assert analysis.json()[0]["status"] == "done"
    assert analysis.json()[0]["provider"] == "metadata"

    detail = await client.get(f"/photos/{photo_id}", headers=admin_headers)
    tag_names = {tag["name"] for tag in detail.json()["tags"]}
    assert "paysage" in tag_names
    assert detail.json()["analysis_status"] == "done"

    # Recherche assistée sur le tag généré par l'analyse.
    found = await client.get("/photos/search", params={"q": "paysage"}, headers=admin_headers)
    assert found.json()["total"] == 1


@pytest.mark.asyncio
async def test_analyze_endpoint_enqueues_job(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    job = await client.post(f"/photos/{photo_id}/analyze", headers=admin_headers)
    assert job.status_code == 201
    assert job.json()["type"] == "analyze"

    await drain_jobs(db_session)
    pending = (await db_session.execute(
        select(PhotoJob).where(PhotoJob.photo_id == photo_id, PhotoJob.status != "done")
    )).scalars().all()
    assert pending == []


# ================================ Personnes / visages ================================

@pytest.mark.asyncio
async def test_people_and_face_assignment(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    created = await client.post(
        "/photos/people", json={"name": "Manu"}, headers=admin_headers
    )
    assert created.status_code == 201
    person_id = created.json()["id"]

    face = PhotoFace(
        photo_id=photo_id, x=0.1, y=0.1, w=0.3, h=0.3,
        confidence=0.9, detector="test",
    )
    db_session.add(face)
    await db_session.commit()
    await db_session.refresh(face)

    assigned = await client.patch(
        f"/photos/faces/{face.id}", json={"person_id": person_id}, headers=admin_headers
    )
    assert assigned.status_code == 200
    assert assigned.json()["person_id"] == person_id

    detail = await client.get(f"/photos/people/{person_id}", headers=admin_headers)
    assert detail.json()["photo_count"] == 1

    by_person = await client.get(
        "/photos", params={"person_id": person_id}, headers=admin_headers
    )
    assert by_person.json()["total"] == 1

    renamed = await client.patch(
        f"/photos/people/{person_id}", json={"name": "Manu P."}, headers=admin_headers
    )
    assert renamed.json()["name"] == "Manu P."

    deleted = await client.delete(f"/photos/people/{person_id}", headers=admin_headers)
    assert deleted.status_code == 204

    await db_session.refresh(face)
    assert face.person_id is None


# ================================ Retouche ================================

@pytest.mark.asyncio
async def test_edit_rotate_creates_version_and_keeps_original(client, db_session, admin_headers):
    data = make_image_bytes(width=120, height=80)
    response = await upload_photo(client, admin_headers, data)
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    from app.services.photo.storage import get_photo_storage

    storage = get_photo_storage()
    original_path = storage.original_path(photo.storage_path)
    original_hash = hashlib.sha256(original_path.read_bytes()).hexdigest()

    edit = await client.post(
        f"/photos/{photo_id}/edits",
        json={"kind": "rotate", "params": {"degrees": 90}, "name": "Rotation"},
        headers=admin_headers,
    )
    assert edit.status_code == 201, edit.text
    assert edit.json()["width"] == 80
    assert edit.json()["height"] == 120
    assert edit.json()["is_active"] is True

    # L'original n'a pas été touché.
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == original_hash

    # La version est téléchargeable.
    version = await client.get(
        f"/photos/{photo_id}/edits/{edit.json()['id']}/file", headers=admin_headers
    )
    assert version.status_code == 200
    assert version.headers["content-type"] == "image/jpeg"

    # Cumul : un second rotate complète le premier (90 + 90 = 180).
    second = await client.post(
        f"/photos/{photo_id}/edits",
        json={"kind": "rotate", "params": {"degrees": 90}},
        headers=admin_headers,
    )
    assert second.status_code == 201
    assert second.json()["width"] == 120
    assert second.json()["height"] == 80

    # Retour à l'original.
    revert = await client.post(f"/photos/{photo_id}/revert", headers=admin_headers)
    assert revert.status_code == 200
    edits = await client.get(f"/photos/{photo_id}/edits", headers=admin_headers)
    assert all(item["is_active"] is False for item in edits.json())


@pytest.mark.asyncio
async def test_edit_auto_enhance(client, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    edit = await client.post(
        f"/photos/{photo_id}/edits",
        json={"kind": "auto_enhance"},
        headers=admin_headers,
    )
    assert edit.status_code == 201, edit.text
    assert edit.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_ai_edit_operations_return_501(client, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    for kind, params in (
        ("ai_remove", {"mask": [0, 0, 10, 10]}),
        ("ai_upscale", {"factor": 2}),
    ):
        edit = await client.post(
            f"/photos/{photo_id}/edits",
            json={"kind": kind, "params": params},
            headers=admin_headers,
        )
        assert edit.status_code == 501, (kind, edit.text)


# ================================ Doublons ================================

@pytest.mark.asyncio
async def test_duplicates_detection(client, admin_headers):
    data = make_image_bytes(color=(200, 100, 50))
    await upload_photo(client, admin_headers, data, filename="a.jpg")
    await upload_photo(client, admin_headers, data, filename="b.jpg")

    duplicates = await client.get("/photos/duplicates", headers=admin_headers)
    assert duplicates.status_code == 200
    groups = duplicates.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["count"] == 2
    assert len(groups[0]["photo_ids"]) == 2


# ================================ Module / navigation ================================

@pytest.mark.asyncio
async def test_navigation_includes_photos_module(client, admin_headers):
    from app.modules import register_all_modules

    register_all_modules()
    response = await client.get("/modules/navigation", headers=admin_headers)
    assert response.status_code == 200
    codes = [item["code"] for item in response.json().get("navigation", [])]
    assert "photos" in codes


@pytest.mark.asyncio
async def test_jobs_listed_for_owner(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    jobs = await client.get("/photos/jobs", headers=admin_headers)
    assert jobs.status_code == 200
    assert any(job["photo_id"] == photo_id for job in jobs.json())

    await drain_jobs(db_session)
    jobs = await client.get("/photos/jobs", headers=admin_headers)
    assert all(job["status"] in ("pending", "running", "failed") for job in jobs.json())


# ================================ Régressions audit technique ================================

@pytest.mark.asyncio
async def test_detail_with_place_returns_200(client, db_session, admin_headers):
    """Régression : accès lazy à photo.place = MissingGreenlet (500) en async."""
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    photo.gps_latitude = 45.5
    photo.gps_longitude = 6.5
    await db_session.commit()
    await enqueue_job(db_session, type="ingest", photo_id=photo_id)
    await drain_jobs(db_session)
    # La session de test est partagée avec l'API : on recharge la relation
    # (en production chaque requête dispose d'une session vierge).
    photo = await db_session.get(Photo, photo_id)
    assert photo.place_id is not None
    await db_session.refresh(photo, ["place"])

    detail = await client.get(f"/photos/{photo_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    place = detail.json()["place"]
    assert place is not None
    assert place["lat_cell"] == 45.5


@pytest.mark.asyncio
async def test_album_rename_duplicate_returns_409(client, admin_headers):
    await client.post("/photos/albums", json={"name": "Alpha"}, headers=admin_headers)
    beta = await client.post("/photos/albums", json={"name": "Beta"}, headers=admin_headers)
    renamed = await client.patch(
        f"/photos/albums/{beta.json()['id']}", json={"name": "Alpha"}, headers=admin_headers
    )
    assert renamed.status_code == 409, renamed.text


@pytest.mark.asyncio
async def test_person_rename_duplicate_returns_409(client, admin_headers):
    await client.post("/photos/people", json={"name": "Jean"}, headers=admin_headers)
    pierre = await client.post("/photos/people", json={"name": "Pierre"}, headers=admin_headers)
    renamed = await client.patch(
        f"/photos/people/{pierre.json()['id']}", json={"name": "Jean"}, headers=admin_headers
    )
    assert renamed.status_code == 409, renamed.text


@pytest.mark.asyncio
async def test_tool_get_photo_returns_tags(client, db_session, admin_headers, admin_user):
    """Régression : detail["tags"] est une liste de dicts, pas de modèles."""
    from app.services.photo.tools import ToolContext, get_photo_tool_registry

    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)
    tagged = await client.post(
        f"/photos/{photo_id}/tags", json={"name": "montagne"}, headers=admin_headers
    )
    assert tagged.status_code == 201, tagged.text

    ctx = ToolContext(db=db_session, user=admin_user, settings=None)
    result = await get_photo_tool_registry().call(ctx, "get_photo", {"photo_id": photo_id})
    assert result.ok, result.error
    assert "montagne" in result.data["tags"]


@pytest.mark.asyncio
async def test_search_endpoint_applies_person_filter(client, db_session, admin_headers):
    """Régression : /photos/search ignorait person_id (filtre frontend perdu)."""
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    person = await client.post(
        "/photos/people", json={"name": "Manu"}, headers=admin_headers
    )
    person_id = person.json()["id"]
    db_session.add(
        PhotoFace(
            photo_id=photo_id, person_id=person_id,
            x=0.1, y=0.1, w=0.3, h=0.3, confidence=0.9, detector="test",
        )
    )
    await db_session.commit()

    matched = await client.get(
        "/photos/search", params={"person_id": person_id}, headers=admin_headers
    )
    assert matched.json()["total"] == 1

    unmatched = await client.get(
        "/photos/search", params={"person_id": person_id + 999}, headers=admin_headers
    )
    assert unmatched.json()["total"] == 0


@pytest.mark.asyncio
async def test_cursor_stays_consistent_with_imported_at_sort(client, db_session, admin_headers):
    """Régression : le curseur encodait taken_at alors que le tri était imported_at."""
    from app.models.user import User
    from app.schemas.photos import PhotoListParams
    from app.services.photo.service import PhotoService

    base = datetime(2024, 1, 1, 12, 0, 0)
    ids = []
    for i in range(5):
        response = await upload_photo(
            client, admin_headers, make_image_bytes(), filename=f"sort{i}.jpg"
        )
        pid = response.json()["items"][0]["id"]
        photo = await db_session.get(Photo, pid)
        # imported_at croissant mais taken_at décroissant (ordres opposés).
        photo.imported_at = base + timedelta(minutes=i)
        photo.taken_at = base - timedelta(days=i)
        await db_session.commit()
        ids.append(pid)
    await drain_jobs(db_session)

    admin = (
        await db_session.execute(select(User).where(User.username == "adminuser"))
    ).scalar_one()
    service = PhotoService(db_session, admin)

    seen: list[int] = []
    cursor = None
    for _ in range(10):
        params = PhotoListParams(
            page_size=2, sort_by="imported_at", sort_order="desc", cursor=cursor
        )
        items, _total, cursor = await service.list_photos(params)
        seen.extend(photo.id for photo in items)
        if not cursor:
            break

    assert sorted(set(seen)) == sorted(set(ids)), f"sauts/doublons: {seen} vs {ids}"
    assert len(seen) == len(set(seen))


@pytest.mark.asyncio
async def test_stale_running_job_is_requeued(client, db_session, admin_headers):
    """Régression : un job 'running' après crash n'était jamais repris."""
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    assert await drain_jobs(db_session) >= 1

    # Simule un processus mort : 'running' plus vieux que le seuil de reprise.
    await db_session.execute(
        sa_update(PhotoJob)
        .where(PhotoJob.photo_id == photo_id, PhotoJob.type == "ingest")
        .values(
            status="running",
            started_at=datetime.now(UTC).replace(tzinfo=None)
            - STALE_RUNNING_AFTER
            - timedelta(minutes=1),
        )
    )
    await db_session.commit()

    requeued = await drain_jobs(db_session)
    assert requeued >= 1, "le job orphelin aurait dû être repris"
    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"


@pytest.mark.asyncio
async def test_download_handles_non_latin1_filename(client, db_session, admin_headers):
    """Régression : nom non latin-1 = UnicodeEncodeError (500) sur Content-Disposition."""
    response = await upload_photo(
        client, admin_headers, make_image_bytes(), filename="写真.jpg"
    )
    assert response.status_code == 201, response.text
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    for params in ({"size": "original", "download": "true"}, {"size": "original"}):
        file_resp = await client.get(
            f"/photos/{photo_id}/file", params=params, headers=admin_headers
        )
        assert file_resp.status_code == 200, file_resp.text
        disposition = file_resp.headers["content-disposition"]
        assert "filename*=UTF-8''" in disposition
        assert disposition.count('"') % 2 == 0


@pytest.mark.asyncio
async def test_upload_leaves_no_orphan_when_job_queue_fails(
    client, db_session, admin_headers, monkeypatch
):
    """Atomicité : photo + job dans une transaction, fichier retiré si échec."""
    from app.services.photo import jobs as photo_jobs
    from app.services.photo.storage import get_photo_storage

    async def broken_enqueue(*args, **kwargs):
        raise RuntimeError("file de jobs indisponible")

    monkeypatch.setattr(photo_jobs, "enqueue_job", broken_enqueue)

    storage = get_photo_storage()
    before = set(storage.originals_root.rglob("*")) if storage.originals_root.exists() else set()

    response = await upload_photo(
        client, admin_headers, make_image_bytes(), filename="orphan.jpg"
    )
    assert response.status_code == 400, response.text
    assert "orphan.jpg" in response.text

    count = (await db_session.execute(select(Photo))).scalars().all()
    assert count == []
    after = set(storage.originals_root.rglob("*")) if storage.originals_root.exists() else set()
    assert after == before
