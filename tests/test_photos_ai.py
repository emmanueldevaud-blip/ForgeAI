"""Tests Photos IA V1 : analyse, qualité, embeddings, similaires, recherche.

Couvre les scénarios demandés : succès / échec / réessai de l'analyse,
ré-analyse (une seule ligne d'indexation), changement de provider,
embedding (création, dédup, changement de modèle), photos similaires
(scores, isolation, photo non indexée), recherche naturelle combinée et
concurrence de jobs.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update as sa_update

from app.models.photo import Photo, PhotoAnalysis, PhotoEmbedding, PhotoJob, PhotoPlace
from app.schemas.photos import PhotoListParams
from app.services.photo import analysis as analysis_module
from app.services.photo.embeddings import (
    get_embedding_provider,
    is_up_to_date,
    run_embedding,
)
from app.services.photo.service import PhotoService
from test_photos import (
    create_limited_user,
    drain_jobs,
    login,
    make_image_bytes,
    upload_photo,
)


class FailingAnalyzer:
    """Analyseur qui échoue toujours (test du mécanisme de retry)."""

    name = "metadata"
    model = "failing"
    version = 1

    async def analyze(self, photo, image_path):
        raise RuntimeError("analyse impossible")


async def _backdate_pending(db, job_type: str) -> None:
    """Annule le backoff d'un job en attente (simule l'écoulement du temps)."""
    await db.execute(
        sa_update(PhotoJob)
        .where(PhotoJob.type == job_type, PhotoJob.status == "pending")
        .values(available_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1))
    )
    await db.commit()


async def _active_jobs(db, photo_id: int, job_type: str) -> list[PhotoJob]:
    result = await db.execute(
        select(PhotoJob).where(
            PhotoJob.photo_id == photo_id,
            PhotoJob.type == job_type,
            PhotoJob.status.in_(("pending", "running")),
        )
    )
    return list(result.scalars().all())


# ================================ Pipeline complet ================================

@pytest.mark.asyncio
async def test_pipeline_analysis_quality_and_embedding(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    assert response.status_code == 201
    photo_id = response.json()["items"][0]["id"]
    assert await drain_jobs(db_session) >= 1

    photo = await db_session.get(Photo, photo_id)
    assert photo.status == "ready"
    assert photo.analysis_status == "done"

    # Analyse qualité : une seule ligne, indexée provider / model / version.
    # (V2 ajoute un second type de ligne, kind="faces", état de détection.)
    analysis = await client.get(f"/photos/{photo_id}/analysis", headers=admin_headers)
    assert analysis.status_code == 200
    rows = [r for r in analysis.json() if r["kind"] == "classification"]
    assert len(rows) == 1
    assert rows[0]["status"] == "done"
    assert rows[0]["provider"] == "metadata"
    assert rows[0]["model"] == "metadata-rules"
    assert rows[0]["version"] == 1
    assert rows[0]["completed_at"] is not None

    # Qualité calculée sur la miniature, bornée à [0, 1].
    quality = rows[0]["result_json"]["quality"]
    assert 0.0 <= quality["overall"] <= 1.0
    for key in ("sharpness", "blur", "exposure", "composition"):
        assert 0.0 <= quality[key] <= 1.0

    # Embedding créé par le job enchaîné.
    embedding = await db_session.get(PhotoEmbedding, photo_id)
    assert embedding is not None
    assert embedding.provider == "local_grid"
    assert embedding.model == "grid-16x16-rgb"
    assert embedding.version == 1
    assert embedding.dimensions == 768
    assert len(embedding.vector_json) == 768


@pytest.mark.asyncio
async def test_analysis_failure_retries_then_fails(
    client, db_session, admin_headers, monkeypatch
):
    """Échec de l'analyse : retries avec backoff, puis échec définitif."""
    monkeypatch.setattr(
        analysis_module, "get_analyzer", lambda *args, **kwargs: FailingAnalyzer()
    )

    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    # Première tentative consommée (backoff actif) : on force les suivantes.
    for _ in range(2):
        await _backdate_pending(db_session, "analyze")
        await drain_jobs(db_session)

    job = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "analyze"
            )
        )
    ).scalar_one()
    assert job.status == "failed"
    assert job.attempts == job.max_attempts == 3
    assert "analyse impossible" in (job.error or "")

    photo = await db_session.get(Photo, photo_id)
    assert photo.analysis_status == "failed"

    analysis = (
        await db_session.execute(
            select(PhotoAnalysis).where(PhotoAnalysis.photo_id == photo_id)
        )
    ).scalar_one()
    assert analysis.status == "failed"
    assert "analyse impossible" in (analysis.error or "")

    # L'analyse a échoué : l'indexation n'a pas été enchaînée.
    assert await db_session.get(PhotoEmbedding, photo_id) is None
    embedding_jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "embedding"
            )
        )
    ).scalars().all()
    assert embedding_jobs == []


@pytest.mark.asyncio
async def test_reanalysis_reuses_single_row(client, db_session, admin_headers):
    """Ré-analyse : la ligne d'indexation est ré-utilisée, pas dupliquée."""
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    reanalyze = await client.post(f"/photos/{photo_id}/analyze", headers=admin_headers)
    assert reanalyze.status_code == 201
    assert reanalyze.json()["type"] == "analyze"
    await drain_jobs(db_session)

    # La ligne qualité n'est pas dupliquée (V2 ajoute une ligne kind="faces").
    rows = (
        await db_session.execute(
            select(PhotoAnalysis).where(
                PhotoAnalysis.photo_id == photo_id,
                PhotoAnalysis.kind == "classification",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "done"

    photo = await db_session.get(Photo, photo_id)
    assert photo.analysis_status == "done"

    # La ré-analyse a aussi ré-enchaîné (ou conservé) l'embedding : une ligne max.
    embeddings = (
        await db_session.execute(
            select(PhotoEmbedding).where(PhotoEmbedding.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(embeddings) == 1


@pytest.mark.asyncio
async def test_analyze_endpoint_deduplicates_pending_jobs(client, db_session, admin_headers):
    """Concurrence : jamais deux jobs « analyze » actifs pour une photo."""
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    first = await client.post(f"/photos/{photo_id}/analyze", headers=admin_headers)
    second = await client.post(f"/photos/{photo_id}/analyze", headers=admin_headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    active = await _active_jobs(db_session, photo_id, "analyze")
    assert len(active) == 1

    # L'ingest enchaîné ne crée pas non plus de doublon.
    await drain_jobs(db_session)
    all_jobs = (
        await db_session.execute(
            select(PhotoJob).where(
                PhotoJob.photo_id == photo_id, PhotoJob.type == "analyze"
            )
        )
    ).scalars().all()
    assert len(all_jobs) == 1
    assert all_jobs[0].status == "done"


# ================================ Embeddings ================================

@pytest.mark.asyncio
async def test_reindex_endpoint_forces_recompute(client, db_session, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)
    assert await db_session.get(PhotoEmbedding, photo_id) is not None

    reindex = await client.post(f"/photos/{photo_id}/embeddings", headers=admin_headers)
    assert reindex.status_code == 201
    assert reindex.json()["type"] == "embedding"
    await drain_jobs(db_session)

    # Upsert : une seule ligne malgré la ré-indexation forcée.
    rows = (
        await db_session.execute(
            select(PhotoEmbedding).where(PhotoEmbedding.photo_id == photo_id)
        )
    ).scalars().all()
    assert len(rows) == 1

    # Dédup : un job « embedding » déjà en file n'en crée pas un second.
    reindex2 = await client.post(f"/photos/{photo_id}/embeddings", headers=admin_headers)
    assert reindex2.status_code == 201
    active = await _active_jobs(db_session, photo_id, "embedding")
    assert len(active) <= 1


@pytest.mark.asyncio
async def test_embedding_model_change_triggers_reindex(client, db_session, admin_headers):
    """Changement de provider/modèle : la ligne est ré-écrite sans force."""
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    photo = await db_session.get(Photo, photo_id)
    provider = get_embedding_provider()
    row = await db_session.get(PhotoEmbedding, photo_id)
    assert row is not None and is_up_to_date(row, provider)

    # Modèle permuté (restauré à la fin du bloc) : ré-indexation automatique.
    from unittest.mock import patch

    with patch.object(provider, "model", "grid-test-v2"):
        assert not is_up_to_date(row, get_embedding_provider())
        recomputed = await run_embedding(db_session, photo)
        assert recomputed is not None
        assert recomputed.model == "grid-test-v2"

    # Provider d'origine restauré : force réaligne la ligne dessus.
    final = await run_embedding(db_session, photo, force=True)
    assert final is not None
    assert final.model == "grid-16x16-rgb"


@pytest.mark.asyncio
async def test_embedding_disabled_returns_none(db_session, admin_user, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "PHOTO_EMBEDDING_ENABLED", False)
    photo = Photo(
        owner_id=admin_user.id,
        original_filename="disabled.jpg",
        storage_path="unused.jpg",
        mime_type="image/jpeg",
        byte_size=1,
        taken_at=datetime.now(),
        content_hash="disabled",
        status="ready",
        analysis_status="pending",
    )
    db_session.add(photo)
    await db_session.commit()
    await db_session.refresh(photo)

    assert await run_embedding(db_session, photo) is None
    assert await db_session.get(PhotoEmbedding, photo.id) is None


# ================================ Photos similaires ================================

@pytest.mark.asyncio
async def test_similar_photos_ranking(client, db_session, admin_headers):
    red = await upload_photo(
        client, admin_headers, make_image_bytes(color=(200, 30, 30)), filename="rouge.jpg"
    )
    red2 = await upload_photo(
        client, admin_headers, make_image_bytes(color=(195, 32, 32)), filename="rouge2.jpg"
    )
    blue = await upload_photo(
        client, admin_headers, make_image_bytes(color=(30, 60, 200)), filename="bleu.jpg"
    )
    red_id = red.json()["items"][0]["id"]
    red2_id = red2.json()["items"][0]["id"]
    blue_id = blue.json()["items"][0]["id"]
    await drain_jobs(db_session)

    similar = await client.get(f"/photos/{red_id}/similar", headers=admin_headers)
    assert similar.status_code == 200
    payload = similar.json()
    assert payload["indexed"] is True
    assert payload["provider"] == "local_grid"
    ids = [item["photo"]["id"] for item in payload["items"]]
    scores = [item["score"] for item in payload["items"]]

    assert red_id not in ids, "la photo source est exclue"
    assert set(ids) == {red2_id, blue_id}
    # Le rouge proche est plus proche que le bleu, scores décroissants.
    assert scores == sorted(scores, reverse=True)
    score_by_id = {item["photo"]["id"]: item["score"] for item in payload["items"]}
    assert score_by_id[red2_id] > score_by_id[blue_id]
    assert all(0.0 < score <= 1.0 for score in scores)


@pytest.mark.asyncio
async def test_similar_on_unindexed_photo(client, admin_headers):
    response = await upload_photo(client, admin_headers, make_image_bytes())
    photo_id = response.json()["items"][0]["id"]

    # Jobs non consommés : pas encore d'embedding.
    similar = await client.get(f"/photos/{photo_id}/similar", headers=admin_headers)
    assert similar.status_code == 200
    payload = similar.json()
    assert payload["indexed"] is False
    assert payload["items"] == []


@pytest.mark.asyncio
async def test_similar_isolated_between_users(client, db_session, admin_headers):
    red = await upload_photo(
        client, admin_headers, make_image_bytes(color=(200, 30, 30))
    )
    red_id = red.json()["items"][0]["id"]

    await create_limited_user(
        db_session, "embed_user", "password123", ["photos.view", "photos.upload"]
    )
    other_headers = await login(client, "embed_user", "password123")
    blue = await upload_photo(
        client, other_headers, make_image_bytes(color=(30, 60, 200))
    )
    blue_id = blue.json()["items"][0]["id"]
    await drain_jobs(db_session)

    # Chez l'admin : aucune photo d'un autre propriétaire.
    similar = await client.get(f"/photos/{red_id}/similar", headers=admin_headers)
    assert similar.status_code == 200
    ids = [item["photo"]["id"] for item in similar.json()["items"]]
    assert blue_id not in ids
    assert similar.json()["indexed"] is True

    # Un autre utilisateur ne peut pas interroger la photo de l'admin.
    forbidden = await client.get(f"/photos/{red_id}/similar", headers=other_headers)
    assert forbidden.status_code == 404


# ================================ Recherche naturelle ================================

@pytest.mark.asyncio
async def test_search_combines_entities_and_free_text(client, db_session, admin_headers):
    response = await upload_photo(
        client, admin_headers, make_image_bytes(), filename="vacances-plage.jpg"
    )
    photo_id = response.json()["items"][0]["id"]
    await drain_jobs(db_session)

    tagged = await client.post(
        f"/photos/{photo_id}/tags", json={"name": "Plage"}, headers=admin_headers
    )
    assert tagged.status_code == 201

    # Tag reconnu comme entité + token restant (« vacances ») sur le nom de fichier.
    combined = await client.get(
        "/photos/search", params={"q": "plage vacances"}, headers=admin_headers
    )
    assert combined.json()["total"] == 1

    # Le texte libre restant est combiné en AND : pas de faux positif.
    strict = await client.get(
        "/photos/search", params={"q": "plage inconnu"}, headers=admin_headers
    )
    assert strict.json()["total"] == 0


@pytest.mark.asyncio
async def test_free_text_matches_place_label(db_session, admin_user):
    photo = Photo(
        owner_id=admin_user.id,
        original_filename="espagne.jpg",
        storage_path="unused.jpg",
        mime_type="image/jpeg",
        byte_size=1,
        taken_at=datetime.now(),
        content_hash="espagne",
        status="ready",
        analysis_status="done",
    )
    db_session.add(photo)
    await db_session.flush()
    place = PhotoPlace(lat_cell=40.4, lon_cell=-3.7, label="Espagne", source="coords")
    db_session.add(place)
    await db_session.flush()
    photo.place_id = place.id
    await db_session.commit()

    service = PhotoService(db_session, admin_user)
    items, total, _ = await service.list_photos(
        PhotoListParams(page_size=10), {"free_text": "espagne"}
    )
    assert total == 1
    assert items[0].id == photo.id

    items, total, _ = await service.list_photos(
        PhotoListParams(page_size=10), {"free_text": "portugal"}
    )
    assert total == 0
