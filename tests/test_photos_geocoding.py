"""Tests du reverse-geocoding des lieux photos (opt-in, cache en base).

Couvre : appel Nominatim mocké (httpx.MockTransport), cache par cellule GPS,
marquage des lieux sans adresse, job ``place_geocode`` et endpoint
``POST /photos/places/geocode``. Aucun appel réseau réel.
"""

import hashlib
from datetime import datetime

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.photo import Photo, PhotoJob, PhotoPlace
from app.services.photo import geocoding
from app.services.photo.jobs import _resolve_place, enqueue_job, process_photo_jobs


# ================================ Helpers ================================

NOMINATIM_ANNENCY = {
    "display_name": "Annecy, Haute-Savoie, France",
    "address": {
        "road": "avenue de la Gare",
        "city": "Annecy",
        "county": "Haute-Savoie",
        "state": "Auvergne-Rhône-Alpes",
        "country": "France",
        "country_code": "fr",
    },
}


@pytest.fixture
def nominatim(monkeypatch):
    """Transport Nominatim mocké + cadence désactivée (tests instantanés)."""
    def _install(payload):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        )
        monkeypatch.setattr(
            geocoding,
            "_build_client",
            lambda: httpx.AsyncClient(transport=transport),
        )
        monkeypatch.setattr(geocoding, "MIN_REQUEST_INTERVAL_SECONDS", 0.0)
        return transport

    return _install


@pytest.fixture
def enable_geocoding(monkeypatch):
    monkeypatch.setattr(get_settings(), "PHOTO_GEOCODING_ENABLED", True)


async def make_pending_place(db, lat=45.9, lon=6.13) -> PhotoPlace:
    place = PhotoPlace(lat_cell=lat, lon_cell=lon, label="", source="coords")
    db.add(place)
    await db.commit()
    return place


def make_gps_photo(owner_id: int, lat: float = 45.9, lon: float = 6.13) -> Photo:
    """Photo minimale flushable (colonnes NOT NULL renseignées)."""
    return Photo(
        owner_id=owner_id,
        original_filename="photo.jpg",
        storage_path="x/photo.jpg",
        mime_type="image/jpeg",
        byte_size=1,
        taken_at=datetime(2024, 6, 1, 12, 0, 0),
        content_hash=hashlib.sha256(b"x").hexdigest(),
        gps_latitude=lat,
        gps_longitude=lon,
    )


# ================================ reverse_geocode ================================

@pytest.mark.asyncio
async def test_reverse_geocode_returns_label_and_country(monkeypatch, nominatim, enable_geocoding):
    nominatim(NOMINATIM_ANNENCY)
    result = await geocoding.reverse_geocode(45.9, 6.13)
    assert result == ("Annecy", "France")


@pytest.mark.asyncio
async def test_reverse_geocode_disabled_returns_none(monkeypatch):
    # Désactivé (défaut conftest) : aucun appel réseau, résultat vide.
    assert get_settings().PHOTO_GEOCODING_ENABLED is False
    assert await geocoding.reverse_geocode(45.9, 6.13) is None


@pytest.mark.asyncio
async def test_reverse_geocode_without_address_returns_none(monkeypatch, nominatim, enable_geocoding):
    # Océan / zone inconnue : Nominatim ne renvoie pas d'adresse exploitable.
    nominatim({"display_name": "North Atlantic Ocean", "lat": "45.9", "lon": "6.13"})
    assert await geocoding.reverse_geocode(45.9, 6.13) is None


@pytest.mark.asyncio
async def test_reverse_geocode_http_404_returns_none(monkeypatch, enable_geocoding):
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    monkeypatch.setattr(
        geocoding, "_build_client", lambda: httpx.AsyncClient(transport=transport)
    )
    monkeypatch.setattr(geocoding, "MIN_REQUEST_INTERVAL_SECONDS", 0.0)
    assert await geocoding.reverse_geocode(45.9, 6.13) is None


# ================================ Cache en base ================================

@pytest.mark.asyncio
async def test_resolve_pending_places_caches_result(db_session, nominatim, enable_geocoding):
    place = await make_pending_place(db_session)
    nominatim(NOMINATIM_ANNENCY)

    resolved, remaining = await geocoding.resolve_pending_places(db_session, limit=10)

    assert (resolved, remaining) == (1, 0)
    await db_session.refresh(place)
    assert place.label == "Annecy"
    assert place.country == "France"
    assert place.source == "nominatim"
    assert place.resolved_at is not None

    # Cache : un second passage ne traite plus rien (aucun nouvel appel).
    assert await geocoding.resolve_pending_places(db_session, limit=10) == (0, 0)


@pytest.mark.asyncio
async def test_resolve_pending_places_marks_unresolved_without_retry(
    db_session, nominatim, enable_geocoding
):
    place = await make_pending_place(db_session, lat=0.0, lon=-30.0)
    nominatim({"display_name": "Atlantic Ocean"})  # aucune clé d'adresse

    resolved, remaining = await geocoding.resolve_pending_places(db_session, limit=10)

    assert (resolved, remaining) == (0, 0)
    await db_session.refresh(place)
    assert place.label == ""
    assert place.source == "nominatim"
    assert place.resolved_at is not None  # marqué traité : jamais retenté


@pytest.mark.asyncio
async def test_resolve_pending_places_disabled_is_noop(db_session):
    place = await make_pending_place(db_session)
    assert await geocoding.resolve_pending_places(db_session, limit=10) == (0, 0)
    await db_session.refresh(place)
    assert place.resolved_at is None


# ================================ Job place_geocode ================================

@pytest.mark.asyncio
async def test_place_geocode_job_resolves_pending_places(db_session, nominatim, enable_geocoding):
    place = await make_pending_place(db_session)
    nominatim(NOMINATIM_ANNENCY)
    await enqueue_job(db_session, type="place_geocode")

    processed = await process_photo_jobs(db_session)

    assert processed == 1
    await db_session.refresh(place)
    assert place.label == "Annecy"
    job = (await db_session.execute(select(PhotoJob))).scalars().one()
    assert job.status == "done"


@pytest.mark.asyncio
async def test_place_geocode_job_disabled_is_noop(db_session):
    await enqueue_job(db_session, type="place_geocode")
    # Désactivé : le job se termine sans appel (aucun lieu créé, aucun réseau).
    assert await process_photo_jobs(db_session) == 1
    job = (await db_session.execute(select(PhotoJob))).scalars().one()
    assert job.status == "done"


@pytest.mark.asyncio
async def test_new_place_enqueues_geocode_job_when_enabled(
    db_session, admin_user, enable_geocoding
):
    photo = make_gps_photo(admin_user.id)
    await _resolve_place(db_session, photo)

    jobs = (
        await db_session.execute(
            select(PhotoJob).where(PhotoJob.type == "place_geocode")
        )
    ).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].status == "pending"


@pytest.mark.asyncio
async def test_new_place_does_not_enqueue_geocode_job_by_default(db_session, admin_user):
    photo = make_gps_photo(admin_user.id)
    await _resolve_place(db_session, photo)

    jobs = (
        await db_session.execute(
            select(PhotoJob).where(PhotoJob.type == "place_geocode")
        )
    ).scalars().all()
    assert jobs == []


# ================================ Endpoint ================================

@pytest.mark.asyncio
async def test_geocode_endpoint_disabled_returns_409(client, admin_headers):
    response = await client.post("/photos/places/geocode", headers=admin_headers)
    assert response.status_code == 409
    assert "PHOTO_GEOCODING_ENABLED" in response.json()["detail"]


@pytest.mark.asyncio
async def test_geocode_endpoint_queues_job_when_pending(
    client, db_session, admin_headers, enable_geocoding
):
    place = await make_pending_place(db_session)

    response = await client.post("/photos/places/geocode", headers=admin_headers)
    assert response.status_code == 202
    body = response.json()
    assert body["queued"] is True
    assert "1 lieu(x) à résoudre" in body["message"]

    # Anti-doublon : le job déjà en file est réutilisé.
    second = await client.post("/photos/places/geocode", headers=admin_headers)
    assert second.status_code == 202
    assert second.json()["queued"] is False

    assert place.resolved_at is None  # le job n'est consommé que par les tests


@pytest.mark.asyncio
async def test_geocode_endpoint_nothing_pending(client, admin_headers, enable_geocoding):
    response = await client.post("/photos/places/geocode", headers=admin_headers)
    assert response.status_code == 202
    assert response.json() == {
        "queued": False,
        "job_id": None,
        "message": "Aucun lieu à résoudre",
    }
