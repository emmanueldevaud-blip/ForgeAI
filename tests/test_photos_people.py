"""Tests Photos V2 — personnes, visages, regroupement, fusion, crops.

Couvre : chaîne de détection (local-first), groupes anonymes auto
(« Personne N »), regroupement par similarité, isolation des groupes
nommés, fusion / renommage / séparation, couvertures, recadrage privé,
compteurs dynamiques (photo en corbeille), recherche par personne,
isolation entre utilisateurs, réessais du job de détection et
ré-indexation après changement de détecteur.
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.photo import Photo, PhotoAnalysis, PhotoFace, PhotoJob, PhotoPerson
from app.services.photo import face_detection
from app.services.photo.face_detection import DetectedFace
from app.services.photo.face_grouping import group_owner_faces
from test_photos import (
    create_limited_user,
    drain_jobs,
    login,
    make_image_bytes,
    upload_photo,
)
from test_photos_ai import _backdate_pending


# ================================ Helpers ================================

class FakeDetector:
    """Détecteur déterministe : renvoie des visages pilotés par le test."""

    def __init__(self, name="fake", model="fake-v1", version=1, faces=()):
        self.name = name
        self.model = model
        self.version = version
        self.dimensions = 4
        self.faces = list(faces)

    async def detect(self, image_path):
        return list(self.faces)


class RaisingDetector(FakeDetector):
    """Détecteur qui échoue toujours (test du mécanisme de retry)."""

    async def detect(self, image_path):
        raise RuntimeError("détection impossible")


def _det(vec=(1.0, 0.0, 0.0, 0.0), x=0.1, y=0.1, w=0.3, h=0.3):
    return DetectedFace(
        x=x, y=y, w=w, h=h, confidence=0.9, embedding=list(vec)
    )


def _install(monkeypatch, *detectors, configured="fake"):
    """Branche des détecteurs factices (registre + setting) pour le test."""
    monkeypatch.setattr(
        face_detection, "_DETECTORS", {d.name: d for d in detectors}
    )
    monkeypatch.setattr(get_settings(), "PHOTO_FACE_DETECTOR", configured)


async def _photo_faces(db, photo_id):
    result = await db.execute(
        select(PhotoFace).where(PhotoFace.photo_id == photo_id).order_by(PhotoFace.id)
    )
    return list(result.scalars().all())


async def _people(db):
    result = await db.execute(select(PhotoPerson).order_by(PhotoPerson.id))
    return list(result.scalars().all())


async def _face_state(db, photo_id):
    return (
        await db.execute(
            select(PhotoAnalysis).where(
                PhotoAnalysis.photo_id == photo_id,
                PhotoAnalysis.kind == "faces",
            )
        )
    ).scalar_one_or_none()


async def _upload(client, db, headers, *, color=(30, 90, 160)):
    response = await upload_photo(client, headers, make_image_bytes(color=color))
    assert response.status_code == 201, response.text
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db)
    return photo_id


# ================================ Chaîne de détection ================================

@pytest.mark.asyncio
async def test_plain_image_runs_face_pipeline_without_faces(
    client, db_session, admin_headers
):
    """Image unie : état kind="faces" créé, 0 visage, aucun groupe auto."""
    photo_id = await _upload(client, db_session, admin_headers)

    state = await _face_state(db_session, photo_id)
    assert state is not None
    assert state.status == "done"
    assert state.provider == "local_heuristic"
    assert (state.result_json or {}).get("faces") == 0

    assert await _photo_faces(db_session, photo_id) == []
    assert await _people(db_session) == []

    jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "face_detect"
            )
        )
    ).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].status == "done"


@pytest.mark.asyncio
async def test_face_detection_disabled_skips_pipeline(
    client, db_session, admin_headers, monkeypatch
):
    """PHOTO_FACE_ENABLED=false : aucun état, aucun job de détection."""
    monkeypatch.setattr(get_settings(), "PHOTO_FACE_ENABLED", False)

    photo_id = await _upload(client, db_session, admin_headers)

    assert await _face_state(db_session, photo_id) is None
    jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id,
                PhotoJob.type.in_(("face_detect", "face_embedding")),
            )
        )
    ).scalars().all()
    assert jobs == []


@pytest.mark.asyncio
async def test_fake_detector_creates_auto_group_with_cover(
    client, db_session, admin_headers, monkeypatch
):
    """1 visage → « Personne 1 », affecté, couverture posée, compteurs OK."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    photo_id = await _upload(client, db_session, admin_headers)

    faces = await _photo_faces(db_session, photo_id)
    assert len(faces) == 1

    people = await _people(db_session)
    assert len(people) == 1
    person = people[0]
    assert person.name == "Personne 1"
    assert faces[0].person_id == person.id
    assert person.cover_face_id == faces[0].id

    listing = await client.get("/photos/people", headers=admin_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    item = listing.json()["items"][0]
    assert item["face_count"] == 1
    assert item["photo_count"] == 1
    assert item["cover_face_id"] == faces[0].id

    face_list = await client.get(
        f"/photos/people/{person.id}/faces", headers=admin_headers
    )
    assert face_list.status_code == 200
    assert face_list.json()["total"] == 1
    assert face_list.json()["items"][0]["id"] == faces[0].id

    detect_jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "face_detect"
            )
        )
    ).scalars().all()
    assert len(detect_jobs) == 1 and detect_jobs[0].status == "done"
    embed_jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "face_embedding"
            )
        )
    ).scalars().all()
    assert len(embed_jobs) == 1 and embed_jobs[0].status == "done"


# ================================ Regroupement ================================

@pytest.mark.asyncio
async def test_dissimilar_faces_create_separate_groups(
    client, db_session, admin_headers, monkeypatch
):
    """Deux vecteurs orthogonaux → deux groupes anonymes distincts."""
    fake = FakeDetector(faces=[_det(vec=(1.0, 0.0, 0.0, 0.0))])
    _install(monkeypatch, fake)
    await _upload(client, db_session, admin_headers, color=(10, 20, 30))

    fake.faces = [_det(vec=(0.0, 1.0, 0.0, 0.0), x=0.5, y=0.5)]
    await _upload(client, db_session, admin_headers, color=(40, 50, 60))

    people = await _people(db_session)
    assert [p.name for p in people] == ["Personne 1", "Personne 2"]
    counts = []
    for person in people:
        face_count, photo_count = await _person_counts(db_session, person.id)
        counts.append((face_count, photo_count))
    assert counts == [(1, 1), (1, 1)]


async def _person_counts(db, person_id):
    """(face_count, photo_count) sur photos non supprimées — comme le service."""
    row = (
        await db.execute(
            select(
                func.count(PhotoFace.id),
                func.count(func.distinct(PhotoFace.photo_id)),
            )
            .join(Photo, Photo.id == PhotoFace.photo_id)
            .where(
                PhotoFace.person_id == person_id,
                Photo.is_deleted.is_(False),
            )
        )
    ).one()
    return int(row[0]), int(row[1])


@pytest.mark.asyncio
async def test_similar_faces_join_same_group_across_photos(
    client, db_session, admin_headers, monkeypatch
):
    """Vecteurs identiques sur deux photos → un seul groupe (2 photos)."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    await _upload(client, db_session, admin_headers, color=(10, 20, 30))
    await _upload(client, db_session, admin_headers, color=(40, 50, 60))

    people = await _people(db_session)
    assert len(people) == 1
    person = people[0]
    assert person.name == "Personne 1"

    detail = await client.get(
        f"/photos/people/{person.id}", headers=admin_headers
    )
    assert detail.json()["face_count"] == 2
    assert detail.json()["photo_count"] == 2


@pytest.mark.asyncio
async def test_named_group_not_joined_automatically(
    client, db_session, admin_headers, monkeypatch
):
    """Un groupe nommé n'est jamais rejoint automatiquement."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    photo_id = await _upload(client, db_session, admin_headers, color=(10, 20, 30))

    people = await _people(db_session)
    person_id = people[0].id
    renamed = await client.patch(
        f"/photos/people/{person_id}",
        json={"name": "Manu"},
        headers=admin_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Manu"

    await _upload(client, db_session, admin_headers, color=(40, 50, 60))

    people = await _people(db_session)
    by_name = {p.name: p for p in people}
    assert set(by_name) == {"Manu", "Personne 1"}
    # Le visage de la première photo est resté chez « Manu ».
    first_faces = await _photo_faces(db_session, photo_id)
    assert first_faces[0].person_id == by_name["Manu"].id


@pytest.mark.asyncio
async def test_auto_merge_similar_anonymous_groups(
    client, db_session, admin_headers
):
    """Deux groupes anonymes très proches (≥ seuil) sont fusionnés."""
    photo_a = await _upload(client, db_session, admin_headers, color=(10, 20, 30))
    photo_b = await _upload(client, db_session, admin_headers, color=(40, 50, 60))

    # Groupes anonymes artificiels quasi identiques (cosinus ≈ 0.9995).
    photo_row = await db_session.get(Photo, photo_a)
    owner_id = photo_row.owner_id
    person_a = PhotoPerson(owner_id=owner_id, name="Personne 1")
    person_b = PhotoPerson(owner_id=owner_id, name="Personne 2")
    db_session.add_all([person_a, person_b])
    await db_session.flush()
    db_session.add(
        PhotoFace(
            photo_id=photo_a,
            x=0.1, y=0.1, w=0.3, h=0.3,
            confidence=0.9, detector="test",
            person_id=person_a.id,
            embedding_json=[1.0, 0.0, 0.0, 0.0],
        )
    )
    db_session.add(
        PhotoFace(
            photo_id=photo_b,
            x=0.5, y=0.5, w=0.3, h=0.3,
            confidence=0.9, detector="test",
            person_id=person_b.id,
            embedding_json=[0.9995, 0.0316, 0.0, 0.0],
        )
    )
    await db_session.commit()

    stats = await group_owner_faces(db_session, owner_id)
    assert stats["merged"] == 1

    people = await _people(db_session)
    assert len(people) == 1
    survivor = people[0]
    assert survivor.name == "Personne 1"
    assert survivor.cover_face_id is not None

    faces = (
        await db_session.execute(
            select(PhotoFace).where(PhotoFace.person_id == survivor.id)
        )
    ).scalars().all()
    assert len(faces) == 2


# ================================ API personnes ================================

@pytest.mark.asyncio
async def test_merge_moves_faces_and_deletes_source(
    client, db_session, admin_headers, monkeypatch
):
    """POST /people/{cible}/merge : la source est absorbée, la cible survit."""
    fake = FakeDetector(faces=[_det(vec=(1.0, 0.0, 0.0, 0.0))])
    _install(monkeypatch, fake)
    await _upload(client, db_session, admin_headers, color=(10, 20, 30))
    fake.faces = [_det(vec=(0.0, 1.0, 0.0, 0.0), x=0.5, y=0.5)]
    await _upload(client, db_session, admin_headers, color=(40, 50, 60))

    listing = await client.get("/photos/people", headers=admin_headers)
    items = listing.json()["items"]
    assert len(items) == 2
    target, source = items[0], items[1]

    merged = await client.post(
        f"/photos/people/{target['id']}/merge",
        json={"person_id": source["id"]},
        headers=admin_headers,
    )
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert body["id"] == target["id"]
    assert body["face_count"] == 2
    assert body["photo_count"] == 2

    gone = await client.get(
        f"/photos/people/{source['id']}", headers=admin_headers
    )
    assert gone.status_code == 404

    listing = await client.get("/photos/people", headers=admin_headers)
    assert listing.json()["total"] == 1


@pytest.mark.asyncio
async def test_merge_adopts_source_name_when_target_is_auto(
    client, db_session, admin_headers, monkeypatch
):
    """Cible auto + source nommée → le nom de la source est adopté."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    await _upload(client, db_session, admin_headers)

    people = await _people(db_session)
    auto = people[0]
    named = await client.post(
        "/photos/people", json={"name": "Manu"}, headers=admin_headers
    )
    assert named.status_code == 201

    merged = await client.post(
        f"/photos/people/{auto.id}/merge",
        json={"person_id": named.json()["id"]},
        headers=admin_headers,
    )
    assert merged.status_code == 200
    assert merged.json()["name"] == "Manu"
    assert merged.json()["face_count"] == 1


@pytest.mark.asyncio
async def test_merge_same_person_rejected(client, db_session, admin_headers):
    created = await client.post(
        "/photos/people", json={"name": "Manu"}, headers=admin_headers
    )
    person_id = created.json()["id"]
    merged = await client.post(
        f"/photos/people/{person_id}/merge",
        json={"person_id": person_id},
        headers=admin_headers,
    )
    assert merged.status_code == 400


@pytest.mark.asyncio
async def test_unassign_face_removes_empty_auto_group(
    client, db_session, admin_headers, monkeypatch
):
    """Séparer le seul visage d'un groupe anonyme supprime le groupe."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    photo_id = await _upload(client, db_session, admin_headers)

    face = (await _photo_faces(db_session, photo_id))[0]
    person_id = face.person_id
    assert person_id is not None

    unassigned = await client.post(
        f"/photos/faces/{face.id}/unassign", headers=admin_headers
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["person_id"] is None

    gone = await client.get(f"/photos/people/{person_id}", headers=admin_headers)
    assert gone.status_code == 404
    listing = await client.get("/photos/people", headers=admin_headers)
    assert listing.json()["total"] == 0

    await db_session.refresh(face)
    assert face.person_id is None


@pytest.mark.asyncio
async def test_set_person_cover_endpoint(
    client, db_session, admin_headers, monkeypatch
):
    """Couverture : visage du groupe accepté, visage d'un autre refusé (400)."""
    fake = FakeDetector(
        faces=[
            _det(vec=(1.0, 0.0, 0.0, 0.0), x=0.1, y=0.1),
            _det(vec=(1.0, 0.0, 0.0, 0.0), x=0.6, y=0.6),
        ]
    )
    _install(monkeypatch, fake)
    photo_id = await _upload(client, db_session, admin_headers)

    faces = await _photo_faces(db_session, photo_id)
    assert len(faces) == 2
    person = (await _people(db_session))[0]
    assert faces[0].person_id == person.id and faces[1].person_id == person.id

    covered = await client.patch(
        f"/photos/people/{person.id}",
        json={"cover_face_id": faces[1].id},
        headers=admin_headers,
    )
    assert covered.status_code == 200
    assert covered.json()["cover_face_id"] == faces[1].id

    cleared = await client.patch(
        f"/photos/people/{person.id}",
        json={"cover_face_id": None},
        headers=admin_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["cover_face_id"] is None

    # Visage d'un autre groupe : refusé.
    fake.faces = [_det(vec=(0.0, 1.0, 0.0, 0.0), x=0.2, y=0.2)]
    await _upload(client, db_session, admin_headers, color=(9, 9, 9))
    other = [p for p in await _people(db_session) if p.id != person.id][0]
    other_faces = (
        await db_session.execute(
            select(PhotoFace).where(PhotoFace.person_id == other.id)
        )
    ).scalars().all()
    rejected = await client.patch(
        f"/photos/people/{person.id}",
        json={"cover_face_id": other_faces[0].id},
        headers=admin_headers,
    )
    assert rejected.status_code == 400


@pytest.mark.asyncio
async def test_delete_photo_neutralizes_person_counts_and_cover(
    client, db_session, admin_headers, monkeypatch
):
    """Photo en corbeille : compteurs à 0, couverture neutralisée."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    photo_id = await _upload(client, db_session, admin_headers)

    person = (await _people(db_session))[0]
    detail = await client.get(f"/photos/people/{person.id}", headers=admin_headers)
    assert detail.json()["face_count"] == 1
    assert detail.json()["photo_count"] == 1
    assert detail.json()["cover_face_id"] is not None

    deleted = await client.delete(f"/photos/{photo_id}", headers=admin_headers)
    assert deleted.status_code == 204

    detail = await client.get(f"/photos/people/{person.id}", headers=admin_headers)
    assert detail.json()["face_count"] == 0
    assert detail.json()["photo_count"] == 0
    assert detail.json()["cover_face_id"] is None


@pytest.mark.asyncio
async def test_search_by_person_name_returns_photos(
    client, db_session, admin_headers, monkeypatch
):
    """Recherche libre « Manu » : résolution du nom de personne (heuristique)."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    await _upload(client, db_session, admin_headers)

    person = (await _people(db_session))[0]
    renamed = await client.patch(
        f"/photos/people/{person.id}",
        json={"name": "Manu"},
        headers=admin_headers,
    )
    assert renamed.status_code == 200

    found = await client.get(
        "/photos/search", params={"q": "Manu"}, headers=admin_headers
    )
    assert found.status_code == 200
    assert found.json()["total"] == 1

    missing = await client.get(
        "/photos/search", params={"q": "Zorro"}, headers=admin_headers
    )
    assert missing.json()["total"] == 0


# ================================ Recadrage / isolation ================================

@pytest.mark.asyncio
async def test_face_crop_endpoint_and_isolation(
    client, db_session, admin_headers, monkeypatch
):
    """Crop JPEG privé : serviable par le propriétaire, 404 pour les autres."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    photo_id = await _upload(client, db_session, admin_headers)
    face = (await _photo_faces(db_session, photo_id))[0]

    crop = await client.get(
        f"/photos/faces/{face.id}/crop", params={"size": "small"},
        headers=admin_headers,
    )
    assert crop.status_code == 200
    assert crop.headers["content-type"] == "image/jpeg"
    assert len(crop.content) > 0
    assert crop.headers.get("cache-control", "").startswith("private")

    await create_limited_user(
        db_session, "bob_face", "password123", ["photos.view", "photos.people.manage"]
    )
    bob_headers = await login(client, "bob_face", "password123")

    denied = await client.get(
        f"/photos/faces/{face.id}/crop", headers=bob_headers
    )
    assert denied.status_code == 404


@pytest.mark.asyncio
async def test_people_isolation_between_users(
    client, db_session, admin_headers, monkeypatch
):
    """Aucun accès aux personnes / visages d'un autre propriétaire."""
    _install(monkeypatch, FakeDetector(faces=[_det()]))
    photo_id = await _upload(client, db_session, admin_headers)
    face = (await _photo_faces(db_session, photo_id))[0]
    person_id = face.person_id

    await create_limited_user(
        db_session, "bob_people", "password123",
        ["photos.view", "photos.people.manage"],
    )
    bob_headers = await login(client, "bob_people", "password123")

    listing = await client.get("/photos/people", headers=bob_headers)
    assert listing.json()["total"] == 0

    assert (
        await client.get(f"/photos/people/{person_id}", headers=bob_headers)
    ).status_code == 404
    assert (
        await client.get(f"/photos/people/{person_id}/faces", headers=bob_headers)
    ).status_code == 404
    assert (
        await client.post(
            f"/photos/people/{person_id}/merge",
            json={"person_id": person_id + 999},
            headers=bob_headers,
        )
    ).status_code == 404
    assert (
        await client.patch(
            f"/photos/people/{person_id}",
            json={"cover_face_id": face.id},
            headers=bob_headers,
        )
    ).status_code == 404
    assert (
        await client.patch(
            f"/photos/faces/{face.id}", json={"person_id": None},
            headers=bob_headers,
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/photos/faces/{face.id}/unassign", headers=bob_headers
        )
    ).status_code == 404
    assert (
        await client.delete(f"/photos/people/{person_id}", headers=bob_headers)
    ).status_code == 404


# ================================ Réessais / ré-indexation ================================

@pytest.mark.asyncio
async def test_face_detect_failure_retries_then_fails(
    client, db_session, admin_headers, monkeypatch
):
    """Échec du détecteur : 3 essais avec backoff, puis échec définitif."""
    _install(monkeypatch, RaisingDetector())
    photo_id = await _upload(client, db_session, admin_headers)

    # La 1ère tentative est déjà consommée (backoff actif) : on force les suivantes.
    for _ in range(2):
        await _backdate_pending(db_session, "face_detect")
        await drain_jobs(db_session)

    job = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "face_detect"
            )
        )
    ).scalar_one()
    assert job.status == "failed"
    assert job.attempts == job.max_attempts == 3
    assert "détection impossible" in (job.error or "")

    state = await _face_state(db_session, photo_id)
    assert state.status == "failed"
    assert "détection impossible" in (state.error or "")

    # Le regroupement n'a jamais été enchaîné.
    embed_jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "face_embedding"
            )
        )
    ).scalars().all()
    assert embed_jobs == []


@pytest.mark.asyncio
async def test_reindex_faces_after_detector_version_change(
    client, db_session, admin_headers, monkeypatch
):
    """Changement de version du détecteur : ré-indexation, groupes nommés conservés."""
    v1 = FakeDetector(model="fake-v1", version=1, faces=[_det()])
    _install(monkeypatch, v1)
    photo_id = await _upload(client, db_session, admin_headers)

    person = (await _people(db_session))[0]
    renamed = await client.patch(
        f"/photos/people/{person.id}",
        json={"name": "Manu"},
        headers=admin_headers,
    )
    assert renamed.status_code == 200

    # Nouvelle version du détecteur : 0 visage sur cette photo.
    v2 = FakeDetector(model="fake-v2", version=2, faces=[])
    _install(monkeypatch, v2)

    reindex = await client.post(f"/photos/{photo_id}/faces", headers=admin_headers)
    assert reindex.status_code == 201, reindex.text
    assert reindex.json()["type"] == "face_detect"
    await drain_jobs(db_session)

    state = await _face_state(db_session, photo_id)
    assert state.status == "done"
    assert state.model == "fake-v2"
    assert state.version == 2

    assert await _photo_faces(db_session, photo_id) == []

    # Le groupe nommé survit (seuls les groupes anonymes vides sont purgés).
    still = await client.get(
        f"/photos/people/{person.id}", headers=admin_headers
    )
    assert still.status_code == 200
    assert still.json()["name"] == "Manu"
    assert still.json()["face_count"] == 0
    assert still.json()["photo_count"] == 0
    assert still.json()["cover_face_id"] is None


# ================================ Frontend ================================

def test_photos_page_imports_createPerson():
    """Régression : createPerson appelé mais absent de l'import (PhotosPage)."""
    page = (
        Path(__file__).resolve().parents[1]
        / "src" / "public" / "js" / "pages" / "PhotosPage.js"
    )
    source = page.read_text(encoding="utf-8")
    import_block = source.split("} from", 1)[0]
    assert "createPerson" in import_block
